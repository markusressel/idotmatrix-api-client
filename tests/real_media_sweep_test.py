"""
Converts every picture and animation of a folder, to see how real-world files behave. Not part of the normal run: set
`IDM_TEST_MEDIA` to a folder (it is searched recursively), f.e.

    IDM_TEST_MEDIA=~/pictures/dpf just test real_media_sweep_test.py

The sizes of the uploads are printed (run pytest with `-s`).
"""
import io
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from PIL import Image

from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode
from tests import TestBase
from tests.gif_module_test import _color_table_sizes

MEDIA_FOLDER = os.environ.get("IDM_TEST_MEDIA")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _files(suffixes: set[str]) -> list[Path]:
    if not MEDIA_FOLDER:
        return []
    folder = Path(MEDIA_FOLDER).expanduser()
    return sorted(path for path in folder.rglob("*") if path.suffix.lower() in suffixes)


@unittest.skipUnless(MEDIA_FOLDER, "set IDM_TEST_MEDIA to a folder of pictures and animations")
class TestRealMedia(TestBase):

    def test_every_gif_converts_to_a_valid_animation(self):
        module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)
        for path in _files({".gif"}):
            with self.subTest(file=path.name):
                data = module._load_gif_and_adapt_to_canvas(
                    file_path=path, canvas_size=64, resize_mode=ResizeMode.FILL)

                result = Image.open(io.BytesIO(data))
                self.assertEqual((64, 64), result.size)
                global_size, local_sizes = _color_table_sizes(data)
                self.assertEqual(256, global_size)
                self.assertEqual({0, 256}, set(local_sizes) | {0, 256})
                print(f"{path.name}: {len(data) / 1024:.0f} KB, {result.n_frames} frames, "
                      f"{result.info.get('duration')} ms each")

    def test_every_picture_converts_to_pixels(self):
        for path in _files(IMAGE_SUFFIXES):
            with self.subTest(file=path.name):
                pixels = ImageModule._load_image_and_adapt_to_canvas(
                    file_path=path, canvas_size=64, resize_mode=ResizeMode.FIT, palletize=False,
                    background_color=(0, 0, 0))

                self.assertEqual(64 * 64 * 3, len(pixels))
