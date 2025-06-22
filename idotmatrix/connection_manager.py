import asyncio
import logging
from collections.abc import Callable
from typing import List, Optional, Awaitable, Any

from bleak import BleakClient, BleakScanner, AdvertisementData

from .const import UUID_READ_DATA, UUID_WRITE_DATA, BLUETOOTH_DEVICE_NAME


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

        self._connection_listeners: List[ConnectionListener] = []

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
        if not self.address:
            self.logging.warning("device address is not set, trying to connect by discovery...")
            await self.connect_by_discovery()
        if not await self.is_connected():
            await self.client.connect()
            self._notify_connection_listeners_connected()
            self.logging.info(f"connected to {self.address}")
        else:
            self.logging.info(f"already connected to {self.address}")

    async def disconnect(self) -> None:
        """
        Disconnects from the device if connected.
        If the client is not connected, this method does nothing.
        """
        if await self.is_connected():
            await self.client.disconnect()

    async def is_connected(self) -> bool:
        """
        Checks if the client is connected to the device.
        Returns:
            bool: True if connected, False otherwise.
        """
        if not self.client:
            return False
        return self.client.is_connected

    async def send_bytes(
        self,
        data: bytearray | bytes,
        response=False,
        chunk_size: Optional[int] = None
    ):
        """
        Sends raw data to the device.

        Args:
            data (bytearray | bytes): The data to send to the device.
            response (bool): If True, a write-with-response operation will be used, otherwise a write-without-response operation will be used.
            chunk_size (Optional[int]): The size of the chunks to split the data into. If None, the maximum write size of the characteristic will be used. Use with care.
        """
        if not await self.is_connected():
            await self.connect()

        self.logging.debug("sending raw data to device")
        if chunk_size is not None:
            ble_packet_size = chunk_size
        else:
            ble_packet_size = self.client.services.get_characteristic(UUID_WRITE_DATA).max_write_without_response_size
        for packet in range(0, len(data), ble_packet_size):
            self.logging.debug(f"sending chunk {packet // ble_packet_size + 1} of {len(data) // ble_packet_size + 1}")
            await self.client.write_gatt_char(UUID_WRITE_DATA, data[packet:packet + ble_packet_size], response=response)

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
        if not await self.is_connected():
            await self.connect()
        self.logging.debug(f"sending {len(packets)} packet(s) to device")
        ble_packet_size = self.client.services.get_characteristic(UUID_WRITE_DATA).max_write_without_response_size
        self.logging.debug(f"ble_packet_size size is {ble_packet_size} bytes")

        for i, packet in enumerate(packets):
            for j, ble_paket in enumerate(packet):
                self.logging.debug(f"sending chunk {i + 1}.{j + 1} of {len(packets)}.{len(packet)}")
                await self.client.write_gatt_char(UUID_WRITE_DATA, ble_paket, response=response)

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
        self.logging.info("notifying connection listeners about connection")
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
        self.logging.info(f"disconnected from {client.address}")
        for listener in self._connection_listeners:
            if listener.on_disconnected:
                asyncio.ensure_future(listener.on_disconnected())
