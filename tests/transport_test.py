from unittest.mock import AsyncMock, MagicMock, patch

from idotmatrix.transport import BleakTransport
from tests import TestBase

ADDRESS = "00:11:22:33:44:55"


def _create_under_test(
    max_write_without_response_size: int,
    mtu_size: int | None = 23,
    acquired_size: int | None = None,
) -> BleakTransport:
    characteristic = MagicMock()
    characteristic.max_write_without_response_size = max_write_without_response_size

    async def acquire_mtu():
        if acquired_size is not None:
            characteristic.max_write_without_response_size = acquired_size

    client = MagicMock()
    client.is_connected = True
    client.mtu_size = mtu_size
    client.services.get_characteristic.return_value = characteristic
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"ok")
    client.start_notify = AsyncMock()
    client._backend = MagicMock(spec=[])
    if acquired_size is not None:
        client._backend._acquire_mtu = acquire_mtu

    with patch("idotmatrix.transport.BleakClient", return_value=client):
        under_test = BleakTransport(ADDRESS, on_disconnected=MagicMock())
    under_test.fake_client = client
    return under_test


class TestBleakTransport(TestBase):

    async def test_creates_a_client_for_the_address(self):
        with patch("idotmatrix.transport.BleakClient") as client_cls:
            BleakTransport(ADDRESS, on_disconnected=MagicMock())

        self.assertEqual(ADDRESS, client_cls.call_args.kwargs["address_or_ble_device"])

    async def test_reports_the_disconnect(self):
        on_disconnected = MagicMock()
        with patch("idotmatrix.transport.BleakClient") as client_cls:
            BleakTransport(ADDRESS, on_disconnected=on_disconnected)

        client_cls.call_args.kwargs["disconnected_callback"](MagicMock())

        on_disconnected.assert_called_once_with()

    async def test_write(self):
        under_test = _create_under_test(max_write_without_response_size=514)

        await under_test.write(b"\x01\x02", response=True)

        under_test.fake_client.write_gatt_char.assert_awaited_once_with(
            char_specifier="0000fa02-0000-1000-8000-00805f9b34fb", data=b"\x01\x02", response=True)

    async def test_read(self):
        under_test = _create_under_test(max_write_without_response_size=514)

        self.assertEqual(b"ok", await under_test.read())

    async def test_notifications_are_passed_on_as_bytes(self):
        under_test = _create_under_test(max_write_without_response_size=514)
        received = []
        await under_test.start_notify(received.append)

        callback = under_test.fake_client.start_notify.await_args.args[1]
        callback(None, bytearray(b"\x05\x00"))

        self.assertEqual([b"\x05\x00"], received)

    async def test_packet_size_uses_reported_write_without_response_size(self):
        under_test = _create_under_test(max_write_without_response_size=244)
        assert await under_test.max_write_without_response_size() == 244

    async def test_packet_size_acquires_mtu_when_default_is_reported(self):
        under_test = _create_under_test(max_write_without_response_size=20, acquired_size=509)
        assert await under_test.max_write_without_response_size() == 509

    async def test_packet_size_falls_back_to_mtu_size(self):
        # macOS Catalina negotiates an ATT MTU of 104, which leaves 101 bytes per write
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=104)
        assert await under_test.max_write_without_response_size() == 101

    async def test_packet_size_keeps_previous_default_when_mtu_is_unknown(self):
        under_test = _create_under_test(max_write_without_response_size=20)
        assert await under_test.max_write_without_response_size() == 514

    async def test_packet_size_falls_back_to_mtu_size_if_acquiring_the_mtu_fails(self):
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=104)
        under_test.fake_client._backend._acquire_mtu = AsyncMock(side_effect=RuntimeError("no mtu exchange"))

        assert await under_test.max_write_without_response_size() == 101

    async def test_packet_size_ignores_default_mtu_size(self):
        # an ATT MTU of 23 is the default before any exchange, so it is not a real measurement
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=23)
        assert await under_test.max_write_without_response_size() == 514

    async def test_packet_size_without_mtu_size(self):
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=None)
        assert await under_test.max_write_without_response_size() == 514


class TestBleakTransportWithDevice(TestBase):

    async def test_connects_with_a_ble_device(self):
        device = MagicMock(address=ADDRESS)
        with patch("idotmatrix.transport.BleakClient") as client_cls:
            under_test = BleakTransport(device, on_disconnected=MagicMock())

        self.assertIs(device, client_cls.call_args.kwargs["address_or_ble_device"])
        self.assertEqual(ADDRESS, under_test.address)
