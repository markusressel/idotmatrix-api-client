import asyncio
import logging
import time
from asyncio import Task
from collections.abc import Callable
from typing import List, Optional, Awaitable, Any

from bleak import BleakScanner, AdvertisementData
from bleak.backends.device import BLEDevice

from .const import BLUETOOTH_DEVICE_NAME
from .transport import Transport, BleakTransport
from .util.command_ack import is_acknowledged_command
from .util.upload_ack import UploadStatus, parse_upload_notification


class ConnectionListener:
    def __init__(
        self,
        on_connected: Optional[Callable[[], Awaitable[Any]]],
        on_disconnected: Optional[Callable[[], Awaitable[Any]]],
    ):
        """
        Initializes the ConnectionListener with optional callbacks for connection events.
        Args:
            on_connected (Optional[Callable[None, Awaitable[Any]]]): Async callback function to be called when connected.
            on_disconnected (Optional[Callable[None, Awaitable[Any]]]): Async callback function to be called when disconnected.
        """
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected


# the official app gives up on an upload if the device does not acknowledge a chunk within 5 seconds
UPLOAD_ACK_TIMEOUT_SECONDS = 5

# the device answers normal commands within a few milliseconds
COMMAND_ACK_TIMEOUT_SECONDS = 1

# a command that the device rejects (status 0) on purpose: it changes nothing, but its answer proves that the device is alive
HEARTBEAT_COMMAND = bytes([5, 0, 4, 128, 255])
HEARTBEAT_ACK_TIMEOUT_SECONDS = 3

RECONNECT_INITIAL_DELAY_SECONDS = 5
RECONNECT_MAX_DELAY_SECONDS = 60


class UploadError(Exception):
    """The device rejected an upload or did not acknowledge it."""


class CommandRejectedError(Exception):
    """The device rejected the arguments of a command."""


class ConnectionManager:
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        address: Optional[str] = None,
        max_ble_packet_size: Optional[int] = None,
        transport_factory: Optional[Callable[[str | BLEDevice, Callable[[], None]], Transport]] = None,
    ) -> None:
        """
        Initializes the ConnectionManager with an optional Bluetooth address.
        Args:
            address (Optional[str]): The Bluetooth address (MAC) of the iDotMatrix device, f.e. "00:11:22:33:44:55".
            If no address is provided, the instance can be used to discover devices and set the address later.
            max_ble_packet_size (Optional[int]): Overrides the maximum payload size of a single write-without-response.
            Only needed if the BLE stack misreports the negotiated MTU. By default, it is detected on connect.
            transport_factory (Optional[Callable[[str | BLEDevice, Callable[[], None]], Transport]]): Creates the
            `Transport` for an address (or a `BLEDevice`, see `set_device`). It gets a callback that has to be called when
            the connection was lost. By default, a `BleakTransport` is used. Use it to connect in a different way, f.e. with
            the client that Home Assistant provides, or to test code against a fake device.
        """
        self._max_ble_packet_size_override = max_ble_packet_size
        self.address: Optional[str] = None
        self._transport_factory = transport_factory or BleakTransport
        self._transport: Optional[Transport] = None
        self._transport_target: str | BLEDevice | None = None  # what to connect to
        self._transport_created_for: str | BLEDevice | None = None  # what the current transport was created for

        if address:
            self.set_address(address)

        self._connected = False
        self._lock = asyncio.Lock()
        # commands and uploads must not be mixed, f.e. an acknowledgement belongs to the last command written
        self._io_lock = asyncio.Lock()

        self._heartbeat_interval: Optional[float] = None
        self._heartbeat_task: Optional[Task] = None
        self._last_activity = time.monotonic()

        self._auto_reconnect = False
        self._is_auto_reconnect_active = False
        self._reconnect_loop_task: Optional[Task] = None

        self._ble_packet_size = None

        self._notifications: asyncio.Queue[bytes] = asyncio.Queue()
        self._notifications_available = False

        self._connection_listeners: List[ConnectionListener] = []

        self._setup_signal_handlers()

    @staticmethod
    async def discover_devices() -> List[str]:
        """
        Discovers iDotMatrix Bluetooth devices.
        Scans for devices with names starting with the defined BLUETOOTH_DEVICE_NAME.
        Returns:
            List[str]: A list of Bluetooth addresses (MAC) of discovered iDotMatrix devices.
        """
        ConnectionManager.logging.info("scanning for iDotMatrix bluetooth devices...")
        devices = await BleakScanner.discover(return_adv=True)
        filtered_devices: List[str] = []
        for key, (device, adv) in devices.items():
            if (
                isinstance(adv, AdvertisementData)
                and adv.local_name
                and str(adv.local_name).startswith(BLUETOOTH_DEVICE_NAME)
            ):
                ConnectionManager.logging.info(f"found device {key} with name {adv.local_name}")
                filtered_devices.append(device.address)
        return filtered_devices

    def set_address(self, address: str) -> None:
        """
        Sets the Bluetooth address (MAC) of the iDotMatrix device.
        Args:
            address (str): The Bluetooth address (MAC) of the iDotMatrix device, f.e. "00:11:22:33:44:55".
        """
        self.address = address
        self._transport_target = address
        self._create_transport()

    def set_device(self, device: BLEDevice) -> None:
        """
        Sets the device to connect to as a `BLEDevice`, f.e. one that a scanner of Home Assistant found, which knows
        how to reach the device (f.e. over a Bluetooth proxy). Call it again with the newer `BLEDevice` when the
        scanner found the device again. An established connection is not interrupted, the new device is used for
        the next connection.
        Args:
            device (BLEDevice): The iDotMatrix device.
        """
        same_device = self.address == device.address
        self.address = device.address
        self._transport_target = device
        if not (same_device and self.is_connected()):
            self._create_transport()

    def _create_transport(self) -> Transport:
        """
        Creates a transport for the address or device that was set, unless the current one already is for it.
        Returns:
            Transport: A transport for the device.
        Raises:
            ValueError: If neither an address nor a device was set.
        """
        target = self._transport_target
        if target is None:
            raise ValueError("No address provided for the transport.")

        if self._transport and self._transport_created_for == target:
            self.logging.debug(f"reusing existing transport for {self.address}")
            return self._transport

        if self._transport:
            # a transport is bound to one device, so a different one needs a new transport
            self._connected = False
            self._ble_packet_size = None

        self._transport = self._transport_factory(target, self._on_disconnected)
        self._transport_created_for = target
        return self._transport

    async def connect_by_address(self, address: str) -> None:
        """
        Connects to the iDotMatrix device using the provided address.
        Args:
            address (str): The Bluetooth address (MAC) of the iDotMatrix device, f.e. "00:11:22:33:44:55".
        """
        self.set_address(address)
        await self.connect()

    async def connect_by_discovery(self) -> str:
        """
        Connects to the first discovered iDotMatrix device.
        If no devices are found, an error message is logged.
        Returns:
            str: The address of the connected device
        Raises:
            AssertionError: If no iDotMatrix devices are found during discovery.
        """
        devices = await self.discover_devices()
        if devices:
            device = devices[0]
            # connect to first device
            self.set_address(device)
            await self.connect()
            return device
        raise AssertionError(
            "No iDotMatrix devices found. Please ensure the device is powered on, in range, and not connected to another device.")

    async def connect(self) -> None:
        """
        Connects to the device using the address set in the ConnectionManager.
        If the client is already connected, it does nothing.
        Raises:
            ValueError: If the device address is not set.
        """
        if not self.address:
            # discovery calls connect() again, so it must run before the (non-reentrant) lock is taken
            self.logging.warning("device address is not set, trying to connect by discovery...")
            await self.connect_by_discovery()
            return

        newly_connected = False
        async with self._lock:
            if self._auto_reconnect:
                self._is_auto_reconnect_active = True

            if not self.is_connected():
                self.logging.info(f"connecting to {self.address}...")
                self._create_transport()  # a newer device may have been set while connected
                await self._transport.connect()
                self._connected = True
                newly_connected = True
                # the negotiated MTU can differ between connections, so it has to be detected again
                self._ble_packet_size = None
                self.logging.info(f"connected to {self.address}")
                self._last_activity = time.monotonic()
                await self._subscribe_to_notifications()
                self._update_heartbeat()
            else:
                self.logging.info(f"already connected to {self.address}")

        if newly_connected:
            self._notify_connection_listeners_connected()

    async def disconnect(self) -> None:
        """
        Disconnects from the device if connected.
        If the client is not connected, this method does nothing.
        """
        # Disable auto-reconnect during active disconnection, it will be re-enabled on active connection attempt
        self._is_auto_reconnect_active = False
        self._stop_heartbeat()
        async with self._lock:
            if self._reconnect_loop_task:
                self._reconnect_loop_task.cancel()
                self._reconnect_loop_task = None
            if self.is_connected():
                await self._transport.disconnect()
            self._connected = False

    def is_connected(self) -> bool:
        """
        Checks if the client is connected to the device.
        Returns:
            bool: True if connected, False otherwise.
        """
        if not self._transport:
            return False
        return self._transport.is_connected or self._connected

    async def send_bytes(
        self,
        data: bytearray | bytes,
        response=False,
        wait_for_ack: bool | None = None,
    ) -> bool:
        """
        Sends raw data to the device.

        Args:
            data (bytearray | bytes): The data to send to the device.
            response (bool): If True, a write-with-response operation will be used, otherwise a write-without-response operation will be used.
            wait_for_ack (bool | None): Whether to wait for the acknowledgement of the device (`05 00 <command> <subcommand> <status>`)
                and raise a `CommandRejectedError` if the device rejected the arguments of the command. By default (None) it is
                waited for commands the device is known to acknowledge (see `util/command_ack.py`). A missing acknowledgement
                is logged, but not an error.
        Returns:
            bool: True if the device acknowledged the command, so it is done with it.
        Raises:
            CommandRejectedError: If the device rejects the command.
        """
        async with self._io_lock:
            if not self.is_connected():
                await self.connect()

            if wait_for_ack is None:
                wait_for_ack = is_acknowledged_command(data)
            wait_for_ack = wait_for_ack and self._notifications_available
            if wait_for_ack:
                # leftovers of earlier commands must not be taken for the acknowledgement of this one
                self._notifications = asyncio.Queue()

            self.logging.debug("sending raw data to device")
            ble_packet_size = await self.get_max_bytes_per_chunk(response)
            chunk_count = -(-len(data) // ble_packet_size)
            for packet in range(0, len(data), ble_packet_size):
                self.logging.debug(f"sending chunk {packet // ble_packet_size + 1} of {chunk_count}")
                await self._transport.write(data[packet:packet + ble_packet_size], response=response)

            return wait_for_ack and await self._wait_for_command_ack(bytes(data))

    async def _wait_for_command_ack(self, command: bytes, timeout: float = None) -> bool:
        """
        Waits for the acknowledgement of a command, which has the form `05 00 <command> <subcommand> <status>`.
        Returns:
            bool: True if the device acknowledged the command, False if it did not answer in time.
        Raises:
            CommandRejectedError: If the device answers with status 0.
        """
        expected = (command[2], command[3])
        try:
            async with asyncio.timeout(timeout or COMMAND_ACK_TIMEOUT_SECONDS):
                while True:
                    notification = await self._notifications.get()
                    if len(notification) >= 5 and notification[0:2] == b"\x05\x00" and \
                            (notification[2], notification[3]) == expected:
                        break
        except TimeoutError:
            self.logging.warning(
                f"the device did not acknowledge the command {command.hex()} within {timeout or COMMAND_ACK_TIMEOUT_SECONDS} seconds")
            return False

        if notification[4] == 0:
            raise CommandRejectedError(
                f"the device rejected the command {command.hex()} (notification {notification.hex()})")
        return True

    async def _subscribe_to_notifications(self) -> None:
        """
        Subscribes to the notifications of the device, which acknowledge the chunks of an upload.
        """
        self._notifications = asyncio.Queue()
        try:
            await self._transport.start_notify(self._on_notification)
            self._notifications_available = True
        except Exception as e:
            self._notifications_available = False
            self.logging.warning(f"could not subscribe to device notifications, uploads are not flow controlled: {e}")

    def _on_notification(self, data: bytes) -> None:
        self.logging.debug(f"received notification: {bytes(data).hex()}")
        self._last_activity = time.monotonic()
        self._notifications.put_nowait(bytes(data))

    async def _wait_for_upload_status(self) -> UploadStatus:
        """
        Waits for the device to acknowledge an upload chunk.
        Raises:
            UploadError: If the device rejects the upload or does not answer in time.
        """
        try:
            async with asyncio.timeout(UPLOAD_ACK_TIMEOUT_SECONDS):
                while True:
                    notification = await self._notifications.get()
                    status = parse_upload_notification(notification)
                    if status is not None:
                        break
        except TimeoutError:
            raise UploadError(
                f"the device did not acknowledge the upload within {UPLOAD_ACK_TIMEOUT_SECONDS} seconds") from None

        if status == UploadStatus.ERROR:
            raise UploadError(f"the device rejected the upload (notification {notification.hex()})")
        return status

    async def send_packets(
        self,
        packets: List[List[bytearray | bytes]],
        response: bool = False,
        wait_for_ack: bool = False,
    ):
        """
        Sends multiple packets to the device.
        Each packet is a list of bytearrays or bytes, which will be sent sequentially.
        The structure of the packets depends on the command being sent to the device.
        If the data needs to be sent in chunks, the caller needs to ensure that the packets are split accordingly.
        Keep in mind that there are two chunking mechanisms:
        1. The outer chunking for the data itself, which is defined in the protocol for a command.
        2. The inner chunking for transmitting over BLE, which is defined by the MTU size of the BLE connection, or the protocol of the command.
        Args:
            packets: A list of packets, where each packet is a list of bytearrays or bytes.
            response: If True, a write-with-response operation will be used, otherwise a write-without-response operation will be used.
            wait_for_ack: If True, the device has to acknowledge each packet before the next one is sent. This is how
                the official app transfers images and GIFs, the device drops or garbles data that is sent too early.
        Raises:
            UploadError: If wait_for_ack is set and the device rejects a packet or does not answer in time.
        """
        async with self._io_lock:
            if len(packets) == 0:
                self.logging.warning("no packets to send, skipping")
                return
            if not self.is_connected():
                await self.connect()

            total_byte_count = 0
            for packet in packets:
                for ble_packet in packet:
                    total_byte_count += len(ble_packet)

            self.logging.debug(
                f"sending {len(packets)} packet(s) in chunks of size {len(packets[0][0])} bytes to device, for a total size of {total_byte_count} bytes"
            )

            # All but the last BLE packet of each packet are sent without response,
            # so every one of them has to fit into a single write-without-response.
            ble_packet_size = await self.get_max_bytes_per_chunk(response=False)
            self.logging.debug(f"ble_packet_size size is {ble_packet_size} bytes")
            packets = self._split_oversized_ble_packets(packets, ble_packet_size)

            wait_for_ack = wait_for_ack and self._notifications_available
            if wait_for_ack:
                # leftovers of earlier commands must not be taken for the acknowledgement of the first packet
                self._notifications = asyncio.Queue()

            for i, packet in enumerate(packets):
                for j, ble_paket in enumerate(packet):
                    self.logging.debug(f"sending packet {i + 1}.{j + 1} of {len(packets)}.{len(packets[-1])}")
                    wait_for_response = response if j == len(packet) - 1 else False
                    await self._transport.write(ble_paket, response=wait_for_response)
                if wait_for_ack:
                    status = await self._wait_for_upload_status()
                    if status == UploadStatus.FINISHED and i < len(packets) - 1:
                        # f.e. the device already has the same data stored
                        self.logging.debug("the device reports the upload as finished, skipping the remaining packets")
                        return

    @staticmethod
    def _split_oversized_ble_packets(
        packets: List[List[bytearray | bytes]],
        max_size: int,
    ) -> List[List[bytearray | bytes]]:
        """
        Splits BLE packets that are larger than max_size into multiple BLE packets.
        Packets that already fit are passed through unchanged, and packets are never merged,
        so commands that rely on their own packet boundaries are not affected.
        The device reassembles the byte stream, so the BLE packet size is not part of the protocol.
        Args:
            packets: A list of packets, where each packet is a list of bytearrays or bytes.
            max_size: The maximum size of a single BLE packet.
        Returns:
            The packets, with every BLE packet being at most max_size bytes long.
        """
        return [
            [
                ble_packet[offset:offset + max_size]
                for ble_packet in packet
                for offset in range(0, max(len(ble_packet), 1), max_size)
            ]
            for packet in packets
        ]

    async def get_max_bytes_per_chunk(self, response: bool) -> int:
        if response:
            # Maximum write size with response is limited to 512 bytes
            # see: https://bleak.readthedocs.io/en/latest/api/client.html#bleak.BleakClient.write_gatt_char
            return 512
        else:
            if self._ble_packet_size is None:
                self._ble_packet_size = await self._detect_max_write_without_response_size()
                self.logging.info(f"using a BLE packet size of {self._ble_packet_size} bytes")

        return self._ble_packet_size

    async def _detect_max_write_without_response_size(self) -> int:
        """
        Determines the maximum payload of a single write-without-response on the current connection.
        """
        if self._max_ble_packet_size_override:
            return self._max_ble_packet_size_override
        return await self._transport.max_write_without_response_size()

    async def read(self) -> bytes:
        if not self._transport.is_connected:
            await self.connect()
        data = await self._transport.read()
        self.logging.info("data received")
        return data

    def add_connection_listener(self, listener: ConnectionListener):
        """
        Adds a connection listener to the ConnectionManager.
        Args:
            listener (ConnectionListener): The listener to be added. It should implement the on_connected and on_disconnected methods.
        """
        self._connection_listeners.append(listener)

    def _notify_connection_listeners_connected(self):
        """
        Notifies all registered connection listeners that the device has been connected.
        """
        for listener in self._connection_listeners:
            if listener.on_connected:
                asyncio.ensure_future(listener.on_connected())

    def _on_disconnected(self):
        """
        Callback function that is called when the transport lost the connection.
        It notifies all registered connection listeners about the disconnection.
        """
        if not self.is_connected():
            return

        self.logging.info(f"disconnected from {self.address}")
        self._handle_disconnect()

    def _handle_disconnect(self):
        """
        Reacts to a lost connection: informs the listeners and starts to reconnect if that is enabled.
        """
        if not self._connected:
            return
        self._connected = False
        self._stop_heartbeat()
        for listener in self._connection_listeners:
            if listener.on_disconnected:
                asyncio.ensure_future(listener.on_disconnected())

        if self._auto_reconnect and self._is_auto_reconnect_active:
            self.logging.info("auto-reconnect is enabled, trying to reconnect...")
            # Start the reconnect loop if not already running
            if self._reconnect_loop_task is None or self._reconnect_loop_task.done():
                self._reconnect_loop_task = asyncio.create_task(self._reconnect_loop())

    def set_heartbeat(self, interval_seconds: Optional[float]) -> None:
        """
        Enables or disables a heartbeat that detects a link that died without the BLE stack noticing, which can
        happen when the device is powered off or goes out of range. While nothing was received from the device for
        the given time, a command is sent that the device answers without changing anything. If the answer is
        missing, the link is closed, the connection listeners are informed and, if enabled, the connection is
        restored (see `set_auto_reconnect`).
        Args:
            interval_seconds (Optional[float]): How long the device may be silent before it is checked, or None to disable.
        Raises:
            ValueError: If the interval is not positive.
        """
        if interval_seconds is not None and interval_seconds <= 0:
            raise ValueError("The heartbeat interval must be greater than 0 seconds.")
        self._heartbeat_interval = interval_seconds
        self._update_heartbeat()

    def _update_heartbeat(self) -> None:
        """Starts or stops the heartbeat task, depending on the settings and the state of the connection."""
        self._stop_heartbeat()
        if self._heartbeat_interval and self._connected and self._notifications_available:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            if self._heartbeat_task is not asyncio.current_task():
                self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self):
        interval = self._heartbeat_interval
        while True:
            # anything the device sends proves that it is alive, so there is no need to ask
            silent_for = time.monotonic() - self._last_activity
            if silent_for < interval:
                await asyncio.sleep(interval - silent_for)
                continue

            if not await self._device_answers():
                self.logging.warning(f"the device does not answer, closing the connection to {self.address}")
                await self._close_dead_link()
                return

    async def _device_answers(self) -> bool:
        try:
            async with self._io_lock:
                self._notifications = asyncio.Queue()
                await self._transport.write(HEARTBEAT_COMMAND, response=True)
                try:
                    return await self._wait_for_command_ack(HEARTBEAT_COMMAND, HEARTBEAT_ACK_TIMEOUT_SECONDS)
                except CommandRejectedError:
                    return True  # rejected on purpose
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logging.warning(f"could not reach the device: {e}")
            return False

    async def _close_dead_link(self):
        """Closes a link that does not work anymore, so that a fresh connection can be made."""
        self._handle_disconnect()
        try:
            async with asyncio.timeout(HEARTBEAT_ACK_TIMEOUT_SECONDS):
                await self._transport.disconnect()
        except Exception as e:
            self.logging.debug(f"error while closing the dead link: {e}")
        # the old transport may still believe that it is connected, so it is not used again
        self._transport = None
        self._create_transport()

    async def _reconnect_loop(self):
        """
        A loop that attempts to reconnect to the device if the connection is lost.
        It will keep trying to reconnect until it succeeds or the auto-reconnect is disabled.
        """
        delay = RECONNECT_INITIAL_DELAY_SECONDS
        while self._auto_reconnect and self._is_auto_reconnect_active and not self.is_connected():
            try:
                await asyncio.sleep(delay)  # Wait before trying to reconnect
                # back off, so a device that is off or out of range is not hammered with attempts
                delay = min(delay * 2, RECONNECT_MAX_DELAY_SECONDS)
                await self.connect()
            except asyncio.CancelledError:
                self.logging.info("Reconnection loop cancelled.")
                break
            except Exception as e:
                self.logging.error(f"Reconnection attempt failed: {e}")

    def set_auto_reconnect(self, auto_reconnect: bool) -> None:
        """
        Sets whether the client should automatically reconnect to the device if the connection is lost.
        Args:
            auto_reconnect (bool): True to enable auto-reconnect, False to disable.
        """
        self._auto_reconnect = auto_reconnect
        self._is_auto_reconnect_active = True

    def _setup_signal_handlers(self):
        """
        Sets up signal handlers for graceful shutdown.
        This is useful to ensure that the connection is properly closed when the application is terminated.
        """
        import signal
        async def async_signal_handler():
            """
            Handles the signal to stop the slideshow gracefully.
            """
            await self.disconnect()

        def signal_handler(signum):
            signame = signal.Signals(signum).name
            logging.info(f'Signal handler called with signal {signame} ({signum})')
            asyncio.ensure_future(async_signal_handler())

        try:
            loop = asyncio.get_event_loop()
            loop.add_signal_handler(signal.SIGINT, lambda: signal_handler(signal.SIGINT))
            loop.add_signal_handler(signal.SIGTERM, lambda: signal_handler(signal.SIGTERM))
        except (NotImplementedError, RuntimeError) as e:
            # NotImplementedError: add_signal_handler() isn't supported on
            # Windows, by any event loop (Proactor or Selector).
            # RuntimeError: no running event loop yet (e.g. ConnectionManager
            # constructed at plain module import time, before an event loop
            # has started).
            logging.debug(f"signal handlers are not supported in this context, skipping: {e}")

