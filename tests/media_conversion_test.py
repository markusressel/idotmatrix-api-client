import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from PIL import Image

from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode, palette_table_size, validate_colors
from tests import TestBase
from tests.gif_module_test import _color_table_sizes
from tests.media_fixtures import GIFS, IMAGES

# every screen and every resize mode is covered, but not every combination of them, which would take long
CASES = (
    (ScreenSize.SIZE_16x16, ResizeMode.FIT),
    (ScreenSize.SIZE_16x16, ResizeMode.FILL),
    (ScreenSize.SIZE_32x32, ResizeMode.STRETCH),
    (ScreenSize.SIZE_64x64, ResizeMode.FIT),
    (ScreenSize.SIZE_64x64, ResizeMode.FILL),
)


class TestConversionOfVariedMedia(TestBase):
    """The conversion has to produce something the device can show, whatever it is given."""

    @classmethod
    def setUpClass(cls):
        # generating the files is a good part of the time these tests take
        cls._tmp = TemporaryDirectory()
        cls.gifs = {name: create(Path(cls._tmp.name) / f"{name}.gif") for name, create in GIFS.items()}
        cls.images = {
            name: create(Path(cls._tmp.name) / f"{name}{'.jpg' if name.endswith('jpg') else '.png'}")
            for name, create in IMAGES.items()
        }

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _gif(self, name: str) -> Path:
        return self.gifs[name]

    def _image(self, name: str) -> Path:
        return self.images[name]

    def test_every_gif_becomes_a_valid_animation_of_the_screen_size(self):
        for name in GIFS:
            file = self._gif(name)
            for screen, resize_mode in CASES:
                with self.subTest(gif=name, screen=screen.name, resize_mode=resize_mode.name):
                    size = screen.value[0]
                    module = GifModule(connection_manager=AsyncMock(), screen_size=screen)

                    data = module._load_gif_and_adapt_to_canvas(
                        file_path=file, canvas_size=size, resize_mode=resize_mode)

                    result = Image.open(io.BytesIO(data))
                    self.assertEqual("GIF", result.format)
                    self.assertEqual((size, size), result.size)
                    self.assertGreaterEqual(result.n_frames, 1)
                    # the device garbles frames if the color tables differ
                    global_size, local_sizes = _color_table_sizes(data)
                    self.assertEqual(256, global_size)
                    self.assertEqual({0, 256}, set(local_sizes) | {0, 256})

    def test_the_frames_of_every_gif_have_a_usable_duration(self):
        for name in GIFS:
            with self.subTest(gif=name):
                module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)

                data = module._load_gif_and_adapt_to_canvas(
                    file_path=self._gif(name), canvas_size=64, resize_mode=ResizeMode.FIT)

                result = Image.open(io.BytesIO(data))
                for frame in range(result.n_frames):
                    result.seek(frame)
                    self.assertGreaterEqual(result.info["duration"], 10)

    def test_all_frames_and_their_own_delays_are_kept(self):
        # GIVEN an animation of 200 frames with alternating delays
        path = Path(self._tmp.name) / "delays.gif"
        frames = [Image.new("RGB", (64, 64), (i, 255 - i, 0)).quantize(256) for i in range(200)]
        delays = [100, 400] * 100
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=delays, loop=0)
        module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)

        # WHEN
        data = module._load_gif_and_adapt_to_canvas(file_path=path, canvas_size=64, resize_mode=ResizeMode.FIT)

        # THEN
        result = Image.open(io.BytesIO(data))
        self.assertEqual(200, result.n_frames)
        got = []
        for frame in range(result.n_frames):
            result.seek(frame)
            got.append(result.info["duration"])
        self.assertEqual(delays, got)

    def test_a_given_duration_is_used_for_all_frames(self):
        module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)

        data = module._load_gif_and_adapt_to_canvas(
            file_path=self._gif(next(iter(GIFS))), canvas_size=64, resize_mode=ResizeMode.FIT,
            duration_per_frame_in_ms=250)

        result = Image.open(io.BytesIO(data))
        for frame in range(result.n_frames):
            result.seek(frame)
            self.assertEqual(250, result.info["duration"])

    def test_frame_durations(self):
        self.assertEqual([100, 100, 16, 130], GifModule._frame_durations([None, 0, 12, 130], None))
        self.assertEqual([70, 70], GifModule._frame_durations([None, 130], 70))

    def test_thinning_out_keeps_the_duration_of_the_loop(self):
        frames = list(range(7))
        durations = [10, 20, 30, 40, 50, 60, 70]

        kept, kept_durations = GifModule._thin_out(frames, durations, 3)

        self.assertEqual([0, 3, 6], kept)
        self.assertEqual([60, 150, 70], kept_durations)
        self.assertEqual(sum(durations), sum(kept_durations))

    def test_a_gif_without_palette_reduction_is_valid_too(self):
        for name in GIFS:
            with self.subTest(gif=name):
                module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)

                data = module._load_gif_and_adapt_to_canvas(
                    file_path=self._gif(name), canvas_size=64, resize_mode=ResizeMode.FIT, palletize=False)

                self.assertEqual((64, 64), Image.open(io.BytesIO(data)).size)

    def test_every_image_becomes_raw_pixels_of_the_screen_size(self):
        for name in IMAGES:
            file = self._image(name)
            for screen, resize_mode in CASES:
                for palletize in (False, True):
                    with self.subTest(image=name, screen=screen.name, resize_mode=resize_mode.name,
                                      palletize=palletize):
                        size = screen.value[0]

                        pixels = ImageModule._load_image_and_adapt_to_canvas(
                            file_path=file,
                            canvas_size=size,
                            resize_mode=resize_mode,
                            palletize=palletize,
                            background_color=(0, 0, 0),
                        )

                        self.assertEqual(size * size * 3, len(pixels))

    def test_transparent_pixels_get_the_background_color(self):
        pixels = ImageModule._load_image_and_adapt_to_canvas(
            file_path=self._image("transparent"),
            canvas_size=32,
            resize_mode=ResizeMode.FIT,
            palletize=False,
            background_color=(255, 0, 0),
        )

        self.assertEqual((255, 0, 0), tuple(pixels[0:3]))


class TestColors(TestBase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.noisy = GIFS["noisy"](Path(cls._tmp.name) / "noisy.gif")
        cls.gradient = GIFS["many_frames"](Path(cls._tmp.name) / "many.gif")
        cls.picture = IMAGES["huge_jpg"](Path(cls._tmp.name) / "huge.jpg")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _encode(self, file: Path, **kwargs) -> bytes:
        module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)
        return module._load_gif_and_adapt_to_canvas(
            file_path=file, canvas_size=64, resize_mode=ResizeMode.FILL, **kwargs)

    def test_fewer_colors_make_the_gif_smaller_and_the_color_tables_smaller(self):
        sizes = {}
        for colors in (256, 64, 16, 2):
            with self.subTest(colors=colors):
                data = self._encode(self.noisy, colors=colors)

                table_size = palette_table_size(colors)
                global_size, local_sizes = _color_table_sizes(data)
                self.assertEqual(table_size, global_size)
                self.assertEqual({0, table_size}, set(local_sizes) | {0, table_size})
                self.assertEqual(Image.open(io.BytesIO(data)).n_frames, len(local_sizes))
                sizes[colors] = len(data)

        self.assertGreater(sizes[256], sizes[64])
        self.assertGreater(sizes[64], sizes[16])
        self.assertGreater(sizes[16], sizes[2])

    def test_fewer_colors_apply_even_without_palletize(self):
        # a palette that is cut to fewer entries than the frame uses would garble the colors
        data = self._encode(self.gradient, palletize=False, colors=16)

        for frame in range(0, Image.open(io.BytesIO(data)).n_frames, 20):
            image = Image.open(io.BytesIO(data))
            image.seek(frame)
            self.assertLessEqual(len(image.convert("RGB").getcolors(maxcolors=4096)), 16)

    def test_table_sizes_are_powers_of_two(self):
        self.assertEqual(
            {2: 4, 3: 4, 4: 4, 5: 8, 16: 16, 17: 32, 255: 256, 256: 256},
            {colors: palette_table_size(colors) for colors in (2, 3, 4, 5, 16, 17, 255, 256)},
        )

    def test_invalid_colors(self):
        for colors in (0, 1, 257, -1, 16.5, "16", True, None):
            with self.subTest(colors=colors):
                with self.assertRaises(ValueError):
                    validate_colors(colors)

    async def test_uploads_reject_invalid_colors(self):
        connection_manager = AsyncMock()
        gif = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        image = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)

        with self.assertRaises(ValueError):
            await gif.upload_gif_file(self.noisy, colors=1)
        with self.assertRaises(ValueError):
            await image.show_image_file(self.picture, colors=300)

        connection_manager.send_packets.assert_not_awaited()

    def test_fewer_colors_reduce_the_colors_of_an_image(self):
        for colors in (2, 8, 64):
            with self.subTest(colors=colors):
                pixels = ImageModule._load_image_and_adapt_to_canvas(
                    file_path=self.picture, canvas_size=64, resize_mode=ResizeMode.FIT, palletize=True,
                    background_color=(0, 0, 0), colors=colors)

                image = Image.frombytes("RGB", (64, 64), bytes(pixels))
                self.assertLessEqual(len(image.getcolors(maxcolors=4096)), colors)


class TestMaxSize(TestBase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.noisy = GIFS["noisy"](Path(cls._tmp.name) / "noisy.gif")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _encode(self, **kwargs) -> bytes:
        module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)
        return module._load_gif_and_adapt_to_canvas(
            file_path=self.noisy, canvas_size=64, resize_mode=ResizeMode.FILL, **kwargs)

    def _info(self, data: bytes) -> tuple[int, int]:
        """The number of frames and the duration of the animation in ms."""
        image = Image.open(io.BytesIO(data))
        total = 0
        for frame in range(image.n_frames):
            image.seek(frame)
            total += image.info["duration"]
        return image.n_frames, total

    def test_a_gif_that_fits_is_left_alone(self):
        data = self._encode()

        self.assertEqual(data, self._encode(max_size_kb=len(data) // 1024 + 1))

    def test_frames_are_given_up_before_colors(self):
        # GIVEN
        data = self._encode()
        frames, duration = self._info(data)

        # WHEN the limit is a bit below the size with all frames
        reduced = self._encode(max_size_kb=int(len(data) * 0.8) // 1024)

        # THEN it fits, with fewer frames and the same duration, but the same colors
        self.assertLessEqual(len(reduced), int(len(data) * 0.8))
        reduced_frames, reduced_duration = self._info(reduced)
        self.assertLess(reduced_frames, frames)
        self.assertGreaterEqual(reduced_frames, 2)
        self.assertEqual(duration, reduced_duration)
        self.assertEqual(_color_table_sizes(data)[0], _color_table_sizes(reduced)[0])

    def test_the_smallest_version_is_used_when_nothing_fits(self):
        with self.assertLogs("idotmatrix.modules.gif", level="WARNING") as logs:
            data = self._encode(max_size_kb=1)

        self.assertIn("does not fit 1 KB", logs.output[0])
        self.assertEqual(8, _color_table_sizes(data)[0])
        self.assertLess(self._info(data)[0], self._info(self._encode())[0])

    def test_reductions_start_with_what_was_asked_for_and_never_exceed_it(self):
        self.assertEqual([(256, 1), (128, 1), (64, 1), (32, 1), (16, 1), (8, 1)], GifModule._size_reductions(256, 1))
        self.assertEqual([(100, 1), (100, 2), (100, 3), (64, 3), (32, 3), (16, 3), (8, 3)],
                         GifModule._size_reductions(100, 7))
        self.assertEqual([(16, 1), (16, 2), (16, 3), (8, 3)], GifModule._size_reductions(16, 7))
        for colors in (256, 100, 16, 4):
            for step_colors, every in GifModule._size_reductions(colors, 40):
                self.assertLessEqual(step_colors, colors)
                self.assertGreaterEqual(40 // every, 2)

    async def test_invalid_max_size(self):
        gif = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)
        for value in (0, -1, 1.5, "10", True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    await gif.upload_gif_file(self.noisy, max_size_kb=value)
