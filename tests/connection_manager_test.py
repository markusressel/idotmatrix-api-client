from unittest.mock import AsyncMock

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
from tests import TestBase
from tests.fake_transport import FakeTransport


def _create_under_test(
    max_write_without_response_size: int,
    max_ble_packet_size: int | None = None,
) -> ConnectionManager:
    transport = FakeTransport(max_write_without_response_size=max_write_without_response_size)

    def factory(address, on_disconnected):
        transport.on_disconnected = on_disconnected
        return transport

    under_test = ConnectionManager(
        address="00:11:22:33:44:55", max_ble_packet_size=max_ble_packet_size, transport_factory=factory)
    transport.is_connected = True
    under_test._transport = transport
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
        calls = under_test._transport.write.await_args_list
        sizes = [len(call.args[0]) for call in calls]
        responses = [call.kwargs["response"] for call in calls]
        assert sizes == [101, 101, 101, 101, 46, 10, 5]
        # only the last BLE packet of each packet waits for a response
        assert responses == [False, False, False, False, False, True, True]
        sent = b"".join(call.args[0] for call in calls[:5])
        assert sent == packets[0][0]

    async def test_send_packets_keeps_ble_packets_that_already_fit(self):
        # GIVEN
        under_test = _create_under_test(max_write_without_response_size=509)
        packets = [[bytes(509), bytes(18), bytes(1)]]

        # WHEN
        await under_test.send_packets(packets=packets, response=False)

        # THEN
        sizes = [len(call.args[0]) for call in under_test._transport.write.await_args_list]
        assert sizes == [509, 18, 1]

    async def test_packet_size_uses_reported_write_without_response_size(self):
        under_test = _create_under_test(max_write_without_response_size=244)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 244

    async def test_packet_size_override(self):
        under_test = _create_under_test(max_write_without_response_size=509, max_ble_packet_size=100)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 100

    async def test_packet_size_is_detected_once_per_connection(self):
        under_test = _create_under_test(max_write_without_response_size=101)

        await under_test.get_max_bytes_per_chunk(response=False)
        await under_test.get_max_bytes_per_chunk(response=False)

        under_test._transport.max_write_without_response_size.assert_awaited_once()

    async def test_packet_size_is_detected_again_after_reconnect(self):
        # GIVEN a connection with a small MTU
        under_test = _create_under_test(max_write_without_response_size=101)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 101

        # WHEN the device reconnects with a larger MTU
        transport = under_test._transport

        async def reconnect():
            transport.is_connected = True
            transport.max_size = 509

        transport.is_connected = False
        under_test._connected = False
        transport.connect = AsyncMock(side_effect=reconnect)
        await under_test.connect()

        # THEN the new limit is used
        assert await under_test.get_max_bytes_per_chunk(response=False) == 509

    async def test_packet_size_override_survives_reconnect(self):
        under_test = _create_under_test(max_write_without_response_size=509, max_ble_packet_size=100)
        assert await under_test.get_max_bytes_per_chunk(response=False) == 100

        under_test._transport.is_connected = False
        under_test._connected = False
        under_test._transport.connect = AsyncMock()
        await under_test.connect()

        assert await under_test.get_max_bytes_per_chunk(response=False) == 100

    async def test_packet_size_with_response_is_not_limited_by_the_mtu(self):
        under_test = _create_under_test(max_write_without_response_size=101)
        assert await under_test.get_max_bytes_per_chunk(response=True) == 512

    async def test_send_bytes_splits_to_the_negotiated_mtu(self):
        under_test = _create_under_test(max_write_without_response_size=101)
        data = bytes(range(256)) * 2

        await under_test.send_bytes(data=data, response=False)

        calls = under_test._transport.write.await_args_list
        assert [len(call.args[0]) for call in calls] == [101, 101, 101, 101, 101, 7]
        assert b"".join(call.args[0] for call in calls) == data

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
    return [(bytes(call.args[0]), call.kwargs["response"])
            for call in under_test._transport.write.await_args_list]


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
