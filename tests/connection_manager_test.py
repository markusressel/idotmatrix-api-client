from unittest.mock import AsyncMock, MagicMock

from idotmatrix.connection_manager import ConnectionManager
from tests import TestBase


def _create_under_test(
    max_write_without_response_size: int,
    mtu_size: int = 23,
    max_ble_packet_size: int | None = None,
    acquired_size: int | None = None,
) -> ConnectionManager:
    under_test = ConnectionManager(max_ble_packet_size=max_ble_packet_size)

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
    client.read_gatt_char = AsyncMock()
    client._backend = MagicMock(spec=[])
    if acquired_size is not None:
        client._backend._acquire_mtu = acquire_mtu

    under_test.client = client
    return under_test


class TestConnectionManager(TestBase):

    async def test_send_packets_splits_ble_packets_larger_than_negotiated_mtu(self):
        # GIVEN
        # macOS Catalina negotiates an ATT MTU of 104, which leaves 101 bytes per write
        under_test = _create_under_test(max_write_without_response_size=101)
        packets = [[bytes(range(200)) + bytes(250), bytes(10)], [bytes(5)]]

        # WHEN
        await under_test.send_packets(packets=packets, response=True)

        # THEN
        calls = under_test.client.write_gatt_char.await_args_list
        sizes = [len(call.kwargs["data"]) for call in calls]
        responses = [call.kwargs["response"] for call in calls]
        assert sizes == [101, 101, 101, 101, 46, 10, 5]
        # only the last BLE packet of each packet waits for a response
        assert responses == [False, False, False, False, False, True, True]
        sent = b"".join(call.kwargs["data"] for call in calls[:5])
        assert sent == packets[0][0]

    async def test_send_packets_keeps_ble_packets_that_already_fit(self):
        # GIVEN
        under_test = _create_under_test(max_write_without_response_size=509)
        packets = [[bytes(509), bytes(18), bytes(1)]]

        # WHEN
        await under_test.send_packets(packets=packets, response=False)

        # THEN
        sizes = [len(call.kwargs["data"]) for call in under_test.client.write_gatt_char.await_args_list]
        assert sizes == [509, 18, 1]

    async def test_packet_size_uses_reported_write_without_response_size(self):
        under_test = _create_under_test(max_write_without_response_size=244)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 244

    async def test_packet_size_acquires_mtu_when_default_is_reported(self):
        under_test = _create_under_test(max_write_without_response_size=20, acquired_size=509)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 509

    async def test_packet_size_falls_back_to_mtu_size(self):
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=104)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 101

    async def test_packet_size_keeps_previous_default_when_mtu_is_unknown(self):
        under_test = _create_under_test(max_write_without_response_size=20)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 514

    async def test_packet_size_override(self):
        under_test = _create_under_test(max_write_without_response_size=509, max_ble_packet_size=100)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 100
