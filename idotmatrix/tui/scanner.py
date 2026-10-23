import logging
from dataclasses import dataclass
from typing import Protocol

from bleak import AdvertisementData, BleakScanner

from idotmatrix.const import BLUETOOTH_DEVICE_NAME

logging = logging.getLogger(__name__)


@dataclass(frozen=True)
class Found:
    """A display that advertises itself."""
    address: str
    name: str
    rssi: int | None


class DeviceScanner(Protocol):
    async def scan(self, seconds: float) -> list[Found]:
        """Listens for `seconds` and returns the displays that advertised, strongest first."""
        ...


class BleakDeviceScanner:
    """Looks for devices with a name that starts with `IDM-`, like `ConnectionManager.discover_devices`."""

    async def scan(self, seconds: float) -> list[Found]:
        found = []
        devices = await BleakScanner.discover(timeout=seconds, return_adv=True)
        for address, (device, advertisement) in devices.items():
            name = str(advertisement.local_name or device.name or "") if isinstance(advertisement, AdvertisementData) else ""
            if name.startswith(BLUETOOTH_DEVICE_NAME):
                found.append(Found(device.address, name, advertisement.rssi))
        found.sort(key=lambda item: item.rssi if item.rssi is not None else -999, reverse=True)
        return found
