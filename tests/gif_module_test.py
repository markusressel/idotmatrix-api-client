import io
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from PIL import Image

from idotmatrix.modules.gif import GifModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode
from tests import TestBase


class TestGifModule(TestBase):

    async def test_upload_gif_file(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = GifModule(
            connection_manager=connection_manager,
            screen_size=ScreenSize.SIZE_64x64,
        )

        # WHEN
        await under_test.upload_gif_file(file_path=self._test_data_folder / "demo.gif")

        # THEN
        connection_manager.send_packets.assert_awaited_once()
        kwargs = connection_manager.send_packets.await_args.kwargs
        self.assertTrue(kwargs["response"])
        self.assertTrue(kwargs["wait_for_ack"])

        # every protocol chunk is a list of BLE packets, with a 16 byte header in front of up to 4096 bytes of GIF
        chunks = [b"".join(ble_packets) for ble_packets in kwargs["packets"]]
        gif = b"".join(chunk[16:] for chunk in chunks)
        for index, chunk in enumerate(chunks):
            self.assertEqual(len(chunk), int.from_bytes(chunk[0:2], "little"))
            self.assertEqual(2 if index else 0, chunk[4])
            self.assertEqual(len(gif), int.from_bytes(chunk[5:9], "little"))
            self.assertEqual(zlib.crc32(gif), int.from_bytes(chunk[9:13], "little"))
            self.assertEqual(12, chunk[15])
            self.assertLessEqual(len(chunk) - 16, 4096)

        image = Image.open(io.BytesIO(gif))
        self.assertEqual((64, 64), image.size)
        self.assertEqual(Image.open(self._test_data_folder / "demo.gif").n_frames, image.n_frames)


def _color_table_sizes(data: bytes) -> tuple[int, list[int]]:
    """Returns the size of the global color table and the sizes of the local ones (0 = frame has none)."""
    position = 13
    global_size = 0
    if data[10] & 0x80:
        global_size = 2 << (data[10] & 7)
        position += 3 * global_size
    local_sizes = []
    while position < len(data) and data[position] != 0x3B:
        if data[position] == 0x21:  # extension block
            position += 2
            while data[position]:
                position += data[position] + 1
            position += 1
        elif data[position] == 0x2C:  # image
            flags = data[position + 9]
            position += 10
            size = 0
            if flags & 0x80:
                size = 2 << (flags & 7)
                position += 3 * size
            local_sizes.append(size)
            position += 1  # LZW minimum code size
            while data[position]:
                position += data[position] + 1
            position += 1
        else:
            raise AssertionError(f"unexpected block {data[position]:#x}")
    return global_size, local_sizes


class TestGifEncoding(TestBase):
    """
    The device garbles or drops frames of GIFs whose color tables differ in size from frame to frame,
    which PIL produces whenever frames use a different number of colors.
    """

    def _create_gif(self, color_counts: list[int]) -> Path:
        frames = []
        for count in color_counts:
            frame = Image.new("RGB", (64, 64))
            for i in range(count):
                frame.paste((i * 7 % 256, i * 13 % 256, i * 29 % 256), (i % 64, 0, i % 64 + 1, 64))
            frames.append(frame.quantize(colors=256))
        path = Path(self._tmp.name) / "source.gif"
        frames[0].save(path, save_all=True, append_images=frames[1:], loop=0, duration=70)
        return path

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.under_test = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)

    def _encode(self, color_counts: list[int], **kwargs) -> bytes:
        return self.under_test._load_gif_and_adapt_to_canvas(
            file_path=self._create_gif(color_counts),
            canvas_size=64,
            resize_mode=ResizeMode.FIT,
            **kwargs,
        )

    def test_all_color_tables_have_the_same_size(self):
        for palletize in (True, False):
            with self.subTest(palletize=palletize):
                data = self._encode([2, 20, 100, 3, 40], palletize=palletize)

                global_size, local_sizes = _color_table_sizes(data)

                self.assertEqual(256, global_size)
                self.assertEqual({0, 256}, set(local_sizes))

    def test_frame_count_and_duration_are_kept(self):
        data = self._encode([2, 20, 100, 3, 40])

        image = Image.open(io.BytesIO(data))

        self.assertEqual(5, image.n_frames)
        self.assertEqual(70, image.info["duration"])
        self.assertEqual(0, image.info["loop"])

    def test_frames_are_not_changed_by_padding_the_palette(self):
        data = self._encode([2, 20, 100], palletize=True)
        source = Image.open(self._create_gif([2, 20, 100]))

        image = Image.open(io.BytesIO(data))
        for index in range(3):
            source.seek(index)
            image.seek(index)
            self.assertEqual(source.convert("RGB").tobytes(), image.convert("RGB").tobytes())
