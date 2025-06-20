import logging
from asyncio import sleep
from typing import List, Optional

from bleak import BleakClient, BleakScanner, AdvertisementData

from .const import UUID_READ_DATA, UUID_WRITE_DATA, BLUETOOTH_DEVICE_NAME


class SingletonMeta(type):
    logging = logging.getLogger(__name__)
    _instances: dict = {}

    def __call__(cls, *args, **kwargs) -> "SingletonMeta":
        if cls not in cls._instances:
            try:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
            except:
                # return None if wrong (or no arguments are given)
                cls._instances[cls] = None
        return cls._instances[cls]


class ConnectionManager(metaclass=SingletonMeta):
    logging = logging.getLogger(__name__)

    def __init__(self) -> None:
        self.address: Optional[str] = None
        self.client: Optional[BleakClient] = None

    @staticmethod
    async def scan() -> List[str]:
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

    async def connectByAddress(self, address: str) -> None:
        self.address = address
        await self.connect()

    async def connectBySearch(self) -> None:
        devices = await self.scan()
        if devices:
            # connect to first device
            self.address = devices[0]
            await self.connect()
        else:
            self.logging.error("no target devices found.")

    async def connect(self) -> None:
        if self.address:
            if not self.client:
                self.client = BleakClient(self.address)
            if not self.client.is_connected:
                await self.client.connect()
                self.logging.info(f"connected to {self.address}")
        else:
            self.logging.error("device address is not set.")

    async def disconnect(self) -> None:
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            self.logging.info(f"disconnected from {self.address}")

    async def send(self, data, response=False):
        if self.client and self.client.is_connected:
            self.logging.debug("sending message(s) to device")
            ble_packet_size = self.client.services.get_characteristic(UUID_WRITE_DATA).max_write_without_response_size
            # if chunk_size < 509:
            ble_packet_size = 509
            self.logging.debug(f"ble_packet_size size is {ble_packet_size} bytes")

            if isinstance(data, list):
                for i, packet in enumerate(data):
                    for j, ble_paket in enumerate(packet):
                        self.logging.debug(f"sending chunk {i + 1}.{j + 1} of {len(data)}.{len(packet)}")
                        await self.client.write_gatt_char(UUID_WRITE_DATA, ble_paket, response=response)
                        await sleep(0.2)
            else:
                for packet in range(0, len(data), ble_packet_size):
                    self.logging.debug(f"sending chunk {packet // ble_packet_size + 1} of {len(data) // ble_packet_size + 1}")
                    await self.client.write_gatt_char(UUID_WRITE_DATA, data[packet:packet + ble_packet_size], response=response)
                    await sleep(0.04)
            return True
        return False

    async def read(self) -> bytes:
        if self.client and self.client.is_connected:
            data = await self.client.read_gatt_char(UUID_READ_DATA)
            self.logging.info("data received")
            return data
        raise ConnectionError("Not connected to the device.")
