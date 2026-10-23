import logging
from collections.abc import Callable
from typing import Protocol

from bleak import BleakClient

from .const import UUID_READ_DATA, UUID_CHARACTERISTIC_WRITE_DATA


class Transport(Protocol):
    """
    The link to one device, as far as the `ConnectionManager` needs it. `BleakTransport` talks to a real device over
    Bluetooth LE, a fake can stand in for it in tests (see `tests/fake_transport.py`).
    """

    @property
    def is_connected(self) -> bool:
        """Whether the link is up, according to the underlying stack."""

    async def connect(self) -> None:
        """Opens the link."""

    async def disconnect(self) -> None:
        """Closes the link."""

    async def write(self, data: bytes | bytearray, response: bool) -> None:
        """
        Writes data to the write characteristic of the device.
        Args:
            data: At most `max_write_without_response_size()` bytes if `response` is False, otherwise at most 512.
            response: True for a write with response, False for a write without response.
        """

    async def read(self) -> bytes:
        """Reads the read characteristic of the device."""

    async def start_notify(self, callback: Callable[[bytes], None]) -> None:
        """Calls `callback` with the payload of every notification of the device."""

    async def max_write_without_response_size(self) -> int:
        """The maximum payload of a single write without response on the current connection."""


class BleakTransport:
    """A `Transport` for a real device, based on `bleak`."""

    logging = logging.getLogger(__name__)

    def __init__(self, address: str, on_disconnected: Callable[[], None]) -> None:
        """
        Args:
            address: The Bluetooth address (MAC) of the device.
            on_disconnected: Called when the connection was lost.
        """
        self.address = address
        self._client = BleakClient(
            address_or_ble_device=address,
            disconnected_callback=lambda _client: on_disconnected(),
        )

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected

    async def connect(self) -> None:
        await self._client.connect()
        # print service and characteristic information for debugging
        for service in self._client.services:
            self.logging.debug(f"Service: {service.uuid} ({service.handle})")
            for characteristic in service.characteristics:
                self.logging.debug(
                    f"  Characteristic: {characteristic.uuid} ({characteristic.handle}): {characteristic.description}")
                self.logging.debug(f"    Properties: {characteristic.properties}")
                self.logging.debug(
                    f"    Max Write Without Response Size: {characteristic.max_write_without_response_size}")

    async def disconnect(self) -> None:
        await self._client.disconnect()

    async def write(self, data: bytes | bytearray, response: bool) -> None:
        await self._client.write_gatt_char(
            char_specifier=UUID_CHARACTERISTIC_WRITE_DATA, data=data, response=response)

    async def read(self) -> bytes:
        return await self._client.read_gatt_char(UUID_READ_DATA)

    async def start_notify(self, callback: Callable[[bytes], None]) -> None:
        await self._client.start_notify(UUID_READ_DATA, lambda _characteristic, data: callback(bytes(data)))

    async def max_write_without_response_size(self) -> int:
        """
        Writes above this size are silently truncated or dropped by some BLE stacks (f.e. macOS Catalina
        negotiates an ATT MTU of 104), so the negotiated MTU is preferred whenever the stack reports one.
        """
        char = self._client.services.get_characteristic(UUID_CHARACTERISTIC_WRITE_DATA)
        size = char.max_write_without_response_size
        if size > 20:
            return size

        # 20 is the default before the MTU exchange has completed. On BlueZ the exchange can be forced.
        acquire_mtu = getattr(self._client._backend, "_acquire_mtu", None)
        if acquire_mtu is not None:
            try:
                await acquire_mtu()
                size = char.max_write_without_response_size
                if size > 20:
                    return size
            except Exception as e:
                self.logging.debug(f"could not acquire MTU: {e}")

        mtu_size = self._client.mtu_size
        if mtu_size and mtu_size > 23:
            # 3 bytes of the ATT MTU are used by the ATT header
            return mtu_size - 3

        # the stack reports no usable MTU at all: keep the previous default,
        # my 64x64 device reports a max_write_without_response_size of 514 bytes, most of the time
        return 514
