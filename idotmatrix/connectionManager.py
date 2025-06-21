import logging
from asyncio import sleep
from typing import List, Optional

from bleak import BleakClient, BleakScanner, AdvertisementData

from .const import UUID_READ_DATA, UUID_WRITE_DATA, BLUETOOTH_DEVICE_NAME


class ConnectionManager:
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.address: Optional[str] = None
        self.client: Optional[BleakClient] = None

    @staticmethod
    async def discover_devices() -> List[str]:
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
        self.address = address
        self._create_ble_client()

    def _create_ble_client(self, address: str = None) -> BleakClient:
        if address is None and self.address is None:
            raise ValueError("No address provided for BleakClient.")
        if address is None:
            address = self.address
        self.client = BleakClient(address)
        return self.client

    async def connect_by_address(self, address: str) -> None:
        self.set_address(address)
        await self.connect()

    async def connect_by_discovery(self) -> None:
        devices = await self.discover_devices()
        if devices:
            # connect to first device
            self.set_address(devices[0])
            await self.connect()
        else:
            self.logging.error("no target devices found.")

    async def connect(self) -> None:
        if not self.address:
            raise ValueError("Device address is not set. Use set_address() or connect_by_address() or connect_by_discovery() first.")
        if not self.is_connected():
            await self.client.connect()
            self.logging.info(f"connected to {self.address}")
        else:
            self.logging.info(f"already connected to {self.address}")

    async def disconnect(self) -> None:
        if await self.is_connected():
            await self.client.disconnect()
            self.logging.info(f"disconnected from {self.address}")

    async def is_connected(self) -> bool:
        if not self.client:
            return False
        return self.client.is_connected

    async def send_bytes(self, data: bytearray | bytes, response=False):
        if not self.address:
            raise ValueError("Device address is not set. Use set_address(), connect_by_address() or connect_by_discovery() first.")
        if not self.client.is_connected:
            await self.connect()

        self.logging.debug("sending message(s) to device")
        ble_packet_size = self.client.services.get_characteristic(UUID_WRITE_DATA).max_write_without_response_size
        for packet in range(0, len(data), ble_packet_size):
            self.logging.debug(f"sending chunk {packet // ble_packet_size + 1} of {len(data) // ble_packet_size + 1}")
            await self.client.write_gatt_char(UUID_WRITE_DATA, data[packet:packet + ble_packet_size], response=response)
            await sleep(0.04)

    async def send_packets(self, packets: List[List[bytearray | bytes]], response=False):
        if not self.client.is_connected:
            await self.connect()
        self.logging.debug("sending message(s) to device")
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
