from PIL import Image as PILImage

from idotmatrix.util import image_utils
from idotmatrix.util.image_utils import ResizeMode
from tests import TestBase

NEAREST = PILImage.Resampling.NEAREST


class TestImageUtils(TestBase):

    def test_palettize(self):
        image = PILImage.new("RGB", (4, 4), (255, 0, 0))
        result = image_utils.palettize(image)
        self.assertEqual("P", result.mode)
        self.assertEqual((4, 4), result.size)

    def test_palettize_rejects_non_image(self):
        with self.assertRaises(TypeError):
            image_utils.palettize("not an image")

    def test_resize_fit_adds_background(self):
        image = PILImage.new("RGB", (20, 10), (255, 0, 0))
        result = image_utils.resize_image(image, 10, ResizeMode.FIT, NEAREST, background_color=(0, 0, 255))
        self.assertEqual((10, 10), result.size)
        self.assertEqual((255, 0, 0), result.getpixel((5, 5)))
        self.assertEqual((0, 0, 255), result.getpixel((5, 0)))
        self.assertEqual((0, 0, 255), result.getpixel((5, 9)))

    def test_resize_fill_crops(self):
        image = PILImage.new("RGB", (20, 10), (255, 0, 0))
        result = image_utils.resize_image(image, 10, ResizeMode.FILL, NEAREST, background_color=(0, 0, 255))
        self.assertEqual((10, 10), result.size)
        for xy in ((0, 0), (9, 0), (0, 9), (9, 9)):
            self.assertEqual((255, 0, 0), result.getpixel(xy))

    def test_resize_stretch(self):
        image = PILImage.new("RGB", (20, 10), (255, 0, 0))
        result = image_utils.resize_image(image, 8, ResizeMode.STRETCH, NEAREST)
        self.assertEqual((8, 8), result.size)
        self.assertEqual((255, 0, 0), result.getpixel((0, 0)))

    def test_resize_transparent_uses_background(self):
        image = PILImage.new("RGBA", (4, 4), (255, 0, 0, 0))
        result = image_utils.resize_image(image, 4, ResizeMode.STRETCH, NEAREST, background_color=(1, 2, 3))
        self.assertEqual((1, 2, 3), result.getpixel((2, 2)))

    def test_resize_output_mode(self):
        image = PILImage.new("RGB", (4, 4))
        result = image_utils.resize_image(image, 4, ResizeMode.FIT, NEAREST, mode="RGBA")
        self.assertEqual("RGBA", result.mode)
