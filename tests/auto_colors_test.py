import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from PIL import Image

from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.modules.materials import MaterialsModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode, palettize_together
from idotmatrix.util.quality import color_difference, color_error, color_score
from tests import TestBase
from tests.gif_module_test import _color_table_sizes
from tests.media_fixtures import GIFS, IMAGES


class TestQuality(TestBase):

    def _gradient(self, shift: int) -> Image.Image:
        image = Image.new("RGB", (32, 32))
        for x in range(32):
            for y in range(32):
                image.putpixel((x, y), ((x * 8 + shift) % 256, y * 8, 100))
        return image

    def test_identical_pictures_have_no_difference(self):
        picture = self._gradient(0)

        self.assertEqual(0, color_difference(picture, picture))
        self.assertEqual((0.0, 0.0), color_error([picture, picture], [picture, picture]))

    def test_the_difference_grows_with_the_distance_of_the_colors(self):
        black = Image.new("RGB", (8, 8), (0, 0, 0))

        near = color_difference(black, Image.new("RGB", (8, 8), (10, 10, 10)))
        far = color_difference(black, Image.new("RGB", (8, 8), (200, 200, 200)))

        self.assertGreater(near, 0)
        self.assertGreater(far, near * 5)

    def test_colors_that_jump_between_frames_are_flicker(self):
        # GIVEN a still picture, and a version of it whose colors alternate from frame to frame
        picture = Image.new("RGB", (8, 8), (100, 100, 100))
        brighter = Image.new("RGB", (8, 8), (130, 130, 130))
        darker = Image.new("RGB", (8, 8), (70, 70, 70))

        # WHEN
        steady_mean, steady_flicker = color_error([picture] * 4, [brighter] * 4)
        mean, flicker = color_error([picture] * 4, [brighter, darker, brighter, darker])

        # THEN the same error with and without flicker, but only the jumping one flickers
        self.assertAlmostEqual(steady_mean, mean, delta=0.5)
        self.assertEqual(0, steady_flicker)
        self.assertGreater(flicker, 5)
        self.assertGreater(color_score(mean, flicker), color_score(steady_mean, steady_flicker))

    def test_a_shared_palette_is_one_palette_for_all_frames(self):
        frames = [self._gradient(shift) for shift in (0, 40, 80)]

        result = palettize_together(frames, colors=16)

        palettes = {tuple(frame.getpalette()[:48]) for frame in result}
        self.assertEqual(1, len(palettes))
        self.assertEqual([f.size for f in frames], [f.size for f in result])


class TestAutoColors(TestBase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.gifs = {name: GIFS[name](Path(cls._tmp.name) / f"{name}.gif") for name in ("pixel_art", "noisy", "flat")}
        cls.module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _encode(self, name: str, **kwargs) -> bytes:
        return self.module._load_gif_and_adapt_to_canvas(
            file_path=self.gifs[name], canvas_size=64, resize_mode=ResizeMode.FILL, **kwargs)

    def test_a_picture_with_few_colors_gets_a_small_palette(self):
        data = self._encode("pixel_art", colors="auto")

        self.assertLessEqual(_color_table_sizes(data)[0], 16)
        self.assertLess(len(data), len(self._encode("pixel_art")))

    def test_the_result_is_within_the_limit_and_smaller_than_with_all_colors(self):
        for name in self.gifs:
            for max_error in (3, 9, 30):
                with self.subTest(gif=name, max_error=max_error):
                    data = self._encode(name, colors="auto", max_color_error=max_error)

                    self.assertLessEqual(len(data), len(self._encode(name)))
                    self.assertEqual(64, Image.open(io.BytesIO(data)).size[0])

    def test_a_higher_limit_never_makes_it_bigger(self):
        for name in self.gifs:
            with self.subTest(gif=name):
                sizes = [len(self._encode(name, colors="auto", max_color_error=e)) for e in (1, 5, 9, 20, 100)]

                self.assertEqual(sorted(sizes, reverse=True), sizes)

    def test_when_nothing_is_good_enough_the_best_is_used_and_it_is_logged(self):
        with self.assertLogs("idotmatrix.modules.gif", level="WARNING") as logs:
            data = self._encode("noisy", colors="auto", max_color_error=-1)

        self.assertIn("no palette is within the color error", logs.output[0])
        self.assertEqual(256, _color_table_sizes(data)[0])

    def test_auto_continues_with_max_size_kb_if_the_chosen_gif_is_too_big(self):
        free = self._encode("noisy", colors="auto", max_color_error=100)

        data = self._encode("noisy", colors="auto", max_color_error=100, max_size_kb=max(len(free) // 1024 // 2, 1))

        self.assertLess(len(data), len(free))

    def test_auto_works_for_an_animation_with_identical_consecutive_frames(self):
        # PIL merges those when it writes a GIF, so the result has fewer frames than the source
        path = Path(self._tmp.name) / "repeated.gif"
        frames = [Image.new("RGB", (64, 64), color) for color in ((255, 0, 0),) * 3 + ((0, 0, 255),) * 3]
        frames[0].save(path, save_all=True, append_images=frames[1:], duration=100, loop=0)

        data = self.module._load_gif_and_adapt_to_canvas(
            file_path=path, canvas_size=64, resize_mode=ResizeMode.FILL, colors="auto")

        self.assertEqual("GIF", Image.open(io.BytesIO(data)).format)

    def test_shared_palette_gives_every_frame_the_same_colors(self):
        data = self._encode("noisy", colors=64, shared_palette=True)

        global_size, local_sizes = _color_table_sizes(data)
        self.assertEqual(64, global_size)
        self.assertTrue(all(local in (0, 64) for local in local_sizes))

    async def test_invalid_colors_are_still_rejected(self):
        gif = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)
        for colors in ("best", 1, 300):
            with self.subTest(colors=colors):
                with self.assertRaises(ValueError):
                    await gif.upload_gif_file(self.gifs["flat"], colors=colors)

    async def test_materials_accepts_auto_for_gifs_and_images(self):
        connection_manager = AsyncMock()
        gif = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        image = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        materials = MaterialsModule(connection_manager=connection_manager, gif=gif, image=image)
        picture = IMAGES["flat"](Path(self._tmp.name) / "flat.png")

        slots = await materials.store([self.gifs["pixel_art"], picture], slots=[0, 1], colors="auto")

        self.assertEqual([0, 1], slots)
        self.assertEqual(2, connection_manager.send_packets.await_count)
