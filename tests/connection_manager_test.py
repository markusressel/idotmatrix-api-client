from unittest.mock import AsyncMock, MagicMock

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
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

    async def test_packet_size_is_detected_once_per_connection(self):
        under_test = _create_under_test(max_write_without_response_size=101)

        await under_test.get_max_bytes_per_chunk(response=False)
        await under_test.get_max_bytes_per_chunk(response=False)

        under_test.client.services.get_characteristic.assert_called_once()

    async def test_packet_size_is_detected_again_after_reconnect(self):
        # GIVEN a connection with a small MTU
        under_test = _create_under_test(max_write_without_response_size=101)
        under_test.address = "00:11:22:33:44:55"
        assert await under_test.get_max_bytes_per_chunk(response=False) == 101

        # WHEN the device reconnects with a larger MTU
        async def reconnect():
            under_test.client.is_connected = True
            under_test.client.services.get_characteristic.return_value.max_write_without_response_size = 509

        under_test.client.is_connected = False
        under_test._connected = False
        under_test.client.connect = AsyncMock(side_effect=reconnect)
        await under_test.connect()

        # THEN the new limit is used
        assert await under_test.get_max_bytes_per_chunk(response=False) == 509

    async def test_packet_size_override_survives_reconnect(self):
        under_test = _create_under_test(max_write_without_response_size=509, max_ble_packet_size=100)
        under_test.address = "00:11:22:33:44:55"
        assert await under_test.get_max_bytes_per_chunk(response=False) == 100

        under_test.client.is_connected = False
        under_test._connected = False
        under_test.client.connect = AsyncMock()
        await under_test.connect()

        assert await under_test.get_max_bytes_per_chunk(response=False) == 100

    async def test_packet_size_override_can_exceed_reported_size(self):
        under_test = _create_under_test(max_write_without_response_size=101, max_ble_packet_size=200)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 200

    async def test_packet_size_falls_back_to_mtu_size_if_acquiring_the_mtu_fails(self):
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=104)
        under_test.client._backend._acquire_mtu = AsyncMock(side_effect=RuntimeError("no mtu exchange"))

        assert await under_test.get_max_bytes_per_chunk(response=False) == 101

    async def test_packet_size_ignores_default_mtu_size(self):
        # an ATT MTU of 23 is the default before any exchange, so it is not a real measurement
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=23)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 514

    async def test_packet_size_without_mtu_size(self):
        under_test = _create_under_test(max_write_without_response_size=20, mtu_size=None)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 514

    async def test_packet_size_with_response_is_not_limited_by_the_mtu(self):
        under_test = _create_under_test(max_write_without_response_size=101)
        assert await under_test.get_max_bytes_per_chunk(response=True) == 512

    async def test_send_bytes_splits_to_the_negotiated_mtu(self):
        under_test = _create_under_test(max_write_without_response_size=101)
        data = bytes(range(256)) * 2

        await under_test.send_bytes(data=data, response=False)

        calls = under_test.client.write_gatt_char.await_args_list
        assert [len(call.kwargs["data"]) for call in calls] == [101, 101, 101, 101, 101, 7]
        assert b"".join(call.kwargs["data"] for call in calls) == data

    async def test_split_keeps_packet_boundaries_and_order(self):
        packets = [[b"a" * 5, b"b" * 3], [b"c" * 4]]

        result = ConnectionManager._split_oversized_ble_packets(packets, 4)

        assert result == [[b"aaaa", b"a", b"bbb"], [b"cccc"]]

    async def test_split_does_not_add_empty_fragments_at_the_boundary(self):
        result = ConnectionManager._split_oversized_ble_packets([[b"a" * 8]], 4)
        assert result == [[b"aaaa", b"aaaa"]]

    async def test_split_keeps_empty_ble_packets(self):
        result = ConnectionManager._split_oversized_ble_packets([[b"", b"ab"]], 4)
        assert result == [[b"", b"ab"]]

    async def test_split_keeps_bytearray_content(self):
        result = ConnectionManager._split_oversized_ble_packets([[bytearray(b"abcde")]], 2)
        assert [bytes(p) for p in result[0]] == [b"ab", b"cd", b"e"]


async def _written_stream(module_factory, upload, max_write_without_response_size: int):
    """
    Runs an upload through a real ConnectionManager against a fake BLE client
    and returns the individual writes as (data, response) tuples.
    """
    under_test = _create_under_test(max_write_without_response_size=max_write_without_response_size)
    module = module_factory(under_test)
    await upload(module)
    return [(bytes(call.kwargs["data"]), call.kwargs["response"])
            for call in under_test.client.write_gatt_char.await_args_list]


class TestSmallMtuUploads(TestBase):
    """
    The image and gif builders always emit 509 byte BLE packets. A host with a small negotiated MTU
    (f.e. macOS Catalina with 101 usable bytes) silently drops anything larger, so all writes have to fit.
    """
    MTU_PAYLOAD = 101

    @staticmethod
    def _pixels(size: int = 32):
        return [(i % 256, (i * 7) % 256, (i * 13) % 256) for i in range(size * size)]

    async def _upload_image(self, size: int):
        return await _written_stream(
            module_factory=lambda cm: ImageModule(connection_manager=cm, screen_size=ScreenSize.SIZE_32x32),
            upload=lambda module: module.upload_image_pixeldata(self._pixels()),
            max_write_without_response_size=size,
        )

    async def _upload_gif(self, size: int):
        return await _written_stream(
            module_factory=lambda cm: GifModule(connection_manager=cm, screen_size=ScreenSize.SIZE_64x64),
            upload=lambda module: module.upload_gif_file(self._test_data_folder / "demo.gif"),
            max_write_without_response_size=size,
        )

    async def test_image_upload_fits_into_small_mtu(self):
        writes = await self._upload_image(self.MTU_PAYLOAD)

        assert max(len(data) for data, _ in writes) <= self.MTU_PAYLOAD

    async def test_gif_upload_fits_into_small_mtu(self):
        writes = await self._upload_gif(self.MTU_PAYLOAD)

        assert max(len(data) for data, _ in writes) <= self.MTU_PAYLOAD

    async def test_image_upload_stream_is_independent_of_the_mtu(self):
        small = await self._upload_image(self.MTU_PAYLOAD)
        large = await self._upload_image(509)

        assert b"".join(d for d, _ in small) == b"".join(d for d, _ in large)
        assert len(small) > len(large)

    async def test_gif_upload_stream_is_independent_of_the_mtu(self):
        small = await self._upload_gif(self.MTU_PAYLOAD)
        large = await self._upload_gif(509)

        assert b"".join(d for d, _ in small) == b"".join(d for d, _ in large)
        assert len(small) > len(large)

    async def test_upload_waits_for_a_response_after_each_protocol_chunk_only(self):
        small = await self._upload_gif(self.MTU_PAYLOAD)
        large = await self._upload_gif(509)

        # splitting must not add or drop acknowledgements
        assert sum(1 for _, response in small if response) == sum(1 for _, response in large if response)
        assert small[-1][1] is True
