import asyncio
import logging
from asyncio import Task
from collections.abc import Callable
from typing import List, Optional, Awaitable, Any

from bleak import BleakClient, BleakScanner, AdvertisementData

from .const import UUID_READ_DATA, UUID_CHARACTERISTIC_WRITE_DATA, BLUETOOTH_DEVICE_NAME
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

RECONNECT_INITIAL_DELAY_SECONDS = 5
RECONNECT_MAX_DELAY_SECONDS = 60


class UploadError(Exception):
    """The device rejected an upload or did not acknowledge it."""


class ConnectionManager:
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        address: Optional[str] = None,
        max_ble_packet_size: Optional[int] = None,
    ) -> None:
        """
        Initializes the ConnectionManager with an optional Bluetooth address.
        Args:
            address (Optional[str]): The Bluetooth address (MAC) of the iDotMatrix device, f.e. "00:11:22:33:44:55".
            If no address is provided, the instance can be used to discover devices and set the address later.
            max_ble_packet_size (Optional[int]): Overrides the maximum payload size of a single write-without-response.
            Only needed if the BLE stack misreports the negotiated MTU. By default, it is detected on connect.
        """
        self._max_ble_packet_size_override = max_ble_packet_size
        self.address: Optional[str] = None
        self.client: Optional[BleakClient] = None
        self._client_address: Optional[str] = None

        if address:
            self.set_address(address)

        self._connected = False
        self._lock = asyncio.Lock()

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
        self._create_ble_client()

    def _create_ble_client(self, address: str = None) -> BleakClient:
        """
        Creates a BleakClient instance for the given address.
        Args:
            address (str, optional): The Bluetooth address (MAC) of the iDotMatrix device. If not provided,
                                     it uses the address set in the ConnectionManager instance.
        Returns:
            BleakClient: An instance of BleakClient connected to the specified address.
        Raises:
            ValueError: If no address is provided and the instance's address is not set.
        """
        if address is None and self.address is None:
            raise ValueError("No address provided for BleakClient.")
        if address is None:
            address = self.address

        if self.client and self._client_address == address:
            self.logging.debug(f"reusing existing client for {address}")
            return self.client

        if self.client:
            # a BleakClient is bound to one address, so a different device needs a new client
            self._connected = False
            self._ble_packet_size = None

        self.client = BleakClient(
            address_or_ble_device=address,
            disconnected_callback=self._on_disconnected
        )
        self._client_address = address
        return self.client

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
                await self.client.connect()
                self._connected = True
                newly_connected = True
                # the negotiated MTU can differ between connections, so it has to be detected again
                self._ble_packet_size = None
                self.logging.info(f"connected to {self.address}")
                await self._subscribe_to_notifications()

                # print service and characteristic information for debugging
                for service in self.client.services:
                    self.logging.debug(f"Service: {service.uuid} ({service.handle})")
                    for characteristic in service.characteristics:
                        self.logging.debug(
                            f"  Characteristic: {characteristic.uuid} ({characteristic.handle}): {characteristic.description}")
                        self.logging.debug(f"    Properties: {characteristic.properties}")
                        self.logging.debug(
                            f"    Max Write Without Response Size: {characteristic.max_write_without_response_size}")
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
        async with self._lock:
            if self._reconnect_loop_task:
                self._reconnect_loop_task.cancel()
                self._reconnect_loop_task = None
            if self.is_connected():
                await self.client.disconnect()
            self._connected = False

    def is_connected(self) -> bool:
        """
        Checks if the client is connected to the device.
        Returns:
            bool: True if connected, False otherwise.
        """
        if not self.client:
            return False
        return self.client.is_connected or self._connected

    async def send_bytes(
        self,
        data: bytearray | bytes,
        response=False,
    ):
        """
        Sends raw data to the device.

        Args:
            data (bytearray | bytes): The data to send to the device.
            response (bool): If True, a write-with-response operation will be used, otherwise a write-without-response operation will be used.
        """
        if not self.is_connected():
            await self.connect()

        self.logging.debug("sending raw data to device")
        ble_packet_size = await self.get_max_bytes_per_chunk(response)
        chunk_count = -(-len(data) // ble_packet_size)
        for packet in range(0, len(data), ble_packet_size):
            self.logging.debug(f"sending chunk {packet // ble_packet_size + 1} of {chunk_count}")
            await self.client.write_gatt_char(
                char_specifier=UUID_CHARACTERISTIC_WRITE_DATA,
                data=data[packet:packet + ble_packet_size],
                response=response)

    async def _subscribe_to_notifications(self) -> None:
        """
        Subscribes to the notifications of the device, which acknowledge the chunks of an upload.
        """
        self._notifications = asyncio.Queue()
        try:
            await self.client.start_notify(UUID_READ_DATA, self._on_notification)
            self._notifications_available = True
        except Exception as e:
            self._notifications_available = False
            self.logging.warning(f"could not subscribe to device notifications, uploads are not flow controlled: {e}")

    def _on_notification(self, _characteristic, data: bytearray) -> None:
        self.logging.debug(f"received notification: {bytes(data).hex()}")
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
                    status = parse_upload_notification(await self._notifications.get())
                    if status is not None:
                        break
        except TimeoutError:
            raise UploadError(
                f"the device did not acknowledge the upload within {UPLOAD_ACK_TIMEOUT_SECONDS} seconds") from None

        if status == UploadStatus.ERROR:
            raise UploadError("the device rejected the upload (is there enough space left?)")
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
                await self.client.write_gatt_char(
                    char_specifier=UUID_CHARACTERISTIC_WRITE_DATA,
                    data=ble_paket,
                    response=wait_for_response
                )
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
        Writes above this size are silently truncated or dropped by some BLE stacks (f.e. macOS Catalina
        negotiates an ATT MTU of 104), so the negotiated MTU is preferred whenever the stack reports one.
        """
        if self._max_ble_packet_size_override:
            return self._max_ble_packet_size_override

        char = self.client.services.get_characteristic(UUID_CHARACTERISTIC_WRITE_DATA)
        size = char.max_write_without_response_size
        if size > 20:
            return size

        # 20 is the default before the MTU exchange has completed. On BlueZ the exchange can be forced.
        acquire_mtu = getattr(self.client._backend, "_acquire_mtu", None)
        if acquire_mtu is not None:
            try:
                await acquire_mtu()
                size = char.max_write_without_response_size
                if size > 20:
                    return size
            except Exception as e:
                self.logging.debug(f"could not acquire MTU: {e}")

        mtu_size = self.client.mtu_size
        if mtu_size and mtu_size > 23:
            # 3 bytes of the ATT MTU are used by the ATT header
            return mtu_size - 3

        # the stack reports no usable MTU at all: keep the previous default,
        # my 64x64 device reports a max_write_without_response_size of 514 bytes, most of the time
        return 514

    async def read(self) -> bytes:
        if not self.client.is_connected:
            await self.connect()
        data = await self.client.read_gatt_char(UUID_READ_DATA)
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

    def _on_disconnected(self, client: BleakClient):
        """
        Callback function that is called when the client is disconnected.
        It notifies all registered connection listeners about the disconnection.
        Args:
            client (BleakClient): The BleakClient instance that was disconnected.
        """
        if not self.is_connected():
            return

        self._connected = False
        self.logging.info(f"disconnected from {client.address}")
        for listener in self._connection_listeners:
            if listener.on_disconnected:
                asyncio.ensure_future(listener.on_disconnected())

        if self._auto_reconnect and self._is_auto_reconnect_active:
            self.logging.info("auto-reconnect is enabled, trying to reconnect...")
            # Start the reconnect loop if not already running
            if self._reconnect_loop_task is None or self._reconnect_loop_task.done():
                self._reconnect_loop_task = asyncio.create_task(self._reconnect_loop())

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

