import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from PIL import Image

from idotmatrix.modules.gif import ANIMATION_MAX_FRAME_COUNT, GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode
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
                    self.assertLessEqual(result.n_frames, ANIMATION_MAX_FRAME_COUNT)
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
                self.assertGreaterEqual(result.info["duration"], 16)

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
