import asyncio
import logging
from asyncio import Task
from collections.abc import Callable
from typing import List, Optional, Awaitable, Any

from bleak import BleakClient, BleakScanner, AdvertisementData
from bleak.exc import BleakDBusError

from .const import UUID_READ_DATA, UUID_CHARACTERISTIC_WRITE_DATA, BLUETOOTH_DEVICE_NAME


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


connection_manager_lock = asyncio.Lock()


class ConnectionManager:
    logging = logging.getLogger(__name__)

    def __init__(
        self,
        address: Optional[str] = None,
    ) -> None:
        """
        Initializes the ConnectionManager with an optional Bluetooth address.
        Args:
            address (Optional[str]): The Bluetooth address (MAC) of the iDotMatrix device, f.e. "00:11:22:33:44:55".
            If no address is provided, the instance can be used to discover devices and set the address later.
        """
        self.address: Optional[str] = None
        self.client: Optional[BleakClient] = None

        if address:
            self.set_address(address)

        self._connected = False

        self._auto_reconnect = False
        self._is_auto_reconnect_active = False
        self._reconnect_loop_task: Optional[Task] = None

        self._ble_packet_size = None

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
        logging.info("scanning for iDotMatrix bluetooth devices...")
        devices = await BleakScanner.discover(return_adv=True)
        filtered_devices: List[str] = []
        for key, (device, adv) in devices.items():
            if (
                isinstance(adv, AdvertisementData)
                and adv.local_name
                and str(adv.local_name).startswith(BLUETOOTH_DEVICE_NAME)
            ):
                logging.info(f"found device {key} with name {adv.local_name}")
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

        if self.client:
            self.client._backend.address = address
            self.logging.debug(f"reusing existing client for {address}")
            return self.client

        self.client = BleakClient(
            address_or_ble_device=address,
            disconnected_callback=self._on_disconnected
        )
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
        async with connection_manager_lock:
            if self._auto_reconnect:
                self._is_auto_reconnect_active = True
            if not self.address:
                self.logging.warning("device address is not set, trying to connect by discovery...")
                await self.connect_by_discovery()

            if not self.is_connected():
                self.logging.info(f"connecting to {self.address}...")
                await self.client.connect()
                self._connected = True
                self.logging.info(f"connected to {self.address}")

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

        self._notify_connection_listeners_connected()

    async def disconnect(self) -> None:
        """
        Disconnects from the device if connected.
        If the client is not connected, this method does nothing.
        """
        # Disable auto-reconnect during active disconnection, it will be re-enabled on active connection attempt
        self._is_auto_reconnect_active = False
        async with connection_manager_lock:
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
        for packet in range(0, len(data), ble_packet_size):
            self.logging.debug(f"sending chunk {packet // ble_packet_size + 1} of {len(data) // ble_packet_size + 1}")
            await self.client.write_gatt_char(
                char_specifier=UUID_CHARACTERISTIC_WRITE_DATA,
                data=data[packet:packet + ble_packet_size],
                response=response)

    async def send_packets(self, packets: List[List[bytearray | bytes]], response: bool = False):
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

        ble_packet_size = await self.get_max_bytes_per_chunk(response)
        self.logging.debug(f"ble_packet_size size is {ble_packet_size} bytes")

        # restructure packets to fit the BLE packet size
        # restructured_packets = []
        # for packet in packets:
        #     restructured_packet = []
        #     # first combine all packets into one bytearray
        #     combined_packet = bytearray()
        #     for ble_packet in packet:
        #         combined_packet.extend(ble_packet)
        #     # then split the combined packet into chunks of size ble_packet_size
        #     for i in range(0, len(combined_packet), ble_packet_size):
        #         restructured_packet.append(combined_packet[i:i + ble_packet_size])
        #     restructured_packets.append(restructured_packet)
        # packets = restructured_packets

        for i, packet in enumerate(packets):
            for j, ble_paket in enumerate(packet):
                self.logging.debug(f"sending packet {i + 1}.{j + 1} of {len(packets)}.{len(packets[-1])}")
                wait_for_response = response if j == len(packet) - 1 else False
                await self.client.write_gatt_char(
                    char_specifier=UUID_CHARACTERISTIC_WRITE_DATA,
                    data=ble_paket,
                    response=wait_for_response
                )
                if wait_for_response:
                    try:
                        response_data = await self.client.read_gatt_char(UUID_READ_DATA)
                        self.logging.debug(f"received response data: {response_data}")
                    except BleakDBusError as e:
                        if e.dbus_error == "org.bluez.Error.NotPermitted":
                            pass
                        else:
                            self.logging.error(f"error while reading response data: {e}")
                            # self.logging.warning("no response received, this is expected for some commands")
                    except Exception as e:
                        self.logging.error(f"error while reading response data: {e}")

    async def get_max_bytes_per_chunk(self, response: bool) -> int:
        if response:
            # Maximum write size with response is limited to 512 bytes
            # see: https://bleak.readthedocs.io/en/latest/api/client.html#bleak.BleakClient.write_gatt_char
            return 512
        else:
            if self._ble_packet_size is None:
                char = self.client.services.get_characteristic(UUID_CHARACTERISTIC_WRITE_DATA)
                if char.max_write_without_response_size != 20:
                    self._ble_packet_size = char.max_write_without_response_size
                else:
                    # my 64x64 device reports a max_write_without_response_size of 514 bytes, most of the time
                    self._ble_packet_size = 514

        return self._ble_packet_size

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
        while self._auto_reconnect and self._is_auto_reconnect_active and not self.is_connected():
            try:
                await asyncio.sleep(5)  # Wait before trying to reconnect
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

        asyncio.get_event_loop().add_signal_handler(signal.SIGINT, lambda: signal_handler(signal.SIGINT))
        asyncio.get_event_loop().add_signal_handler(signal.SIGTERM, lambda: signal_handler(signal.SIGTERM))
