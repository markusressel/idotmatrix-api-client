import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from PIL import Image, ImageChops

from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.modules.materials import MaterialsModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.util.image_utils import ResizeMode
from idotmatrix.util.overlay import POSITIONS, TextOverlay
from tests import TestBase
from tests.media_fixtures import GIFS


def _black(size: int = 64) -> Image.Image:
    return Image.new("RGB", (size, size), (0, 0, 0))


def _changed_box(image: Image.Image) -> tuple[int, int, int, int] | None:
    """The area that differs from a black picture."""
    return ImageChops.difference(image.convert("RGB"), _black(image.width)).getbbox()


class TestTextOverlay(TestBase):

    def test_the_text_is_drawn_in_the_corner_it_is_asked_for(self):
        expectations = {
            "top-left": lambda box: box[0] <= 2 and box[1] <= 2,
            "top-right": lambda box: box[2] >= 61 and box[1] <= 2,
            "bottom-left": lambda box: box[0] <= 2 and box[3] >= 61,
            "bottom-right": lambda box: box[2] >= 61 and box[3] >= 61,
            "top-center": lambda box: abs((box[0] + box[2]) / 2 - 32) <= 2 and box[1] <= 2,
            "bottom-center": lambda box: abs((box[0] + box[2]) / 2 - 32) <= 2 and box[3] >= 61,
            "center": lambda box: abs((box[0] + box[2]) / 2 - 32) <= 2 and abs((box[1] + box[3]) / 2 - 32) <= 2,
        }
        self.assertEqual(set(POSITIONS), set(expectations))
        for position, is_there in expectations.items():
            with self.subTest(position=position):
                result = TextOverlay("Hi", position=position, background=None).apply(_black())

                box = _changed_box(result)
                self.assertIsNotNone(box)
                self.assertTrue(is_there(box), box)

    def test_the_text_has_its_color_and_no_anti_aliasing(self):
        result = TextOverlay("Hi", color=(255, 0, 0), background=None).apply(_black())

        self.assertEqual({(0, 0, 0), (255, 0, 0)}, {color for _, color in result.convert("RGB").getcolors()})

    def test_the_background_box_is_blended_over_the_picture(self):
        white = Image.new("RGB", (64, 64), (255, 255, 255))

        result = TextOverlay("Hi", background=(0, 0, 0, 128), color=(255, 255, 255)).apply(white).convert("RGB")

        # the box darkens what is behind it by half, the text itself stays white
        colors = {color for _, color in result.getcolors()}
        self.assertIn((255, 255, 255), colors)
        self.assertTrue(any(120 <= r <= 135 for r, _, _ in colors), colors)

    def test_without_background_only_the_text_changes_something(self):
        with_box = TextOverlay("Hi", background=(0, 0, 0, 255)).apply(Image.new("RGB", (64, 64), (9, 9, 9)))
        without = TextOverlay("Hi", background=None).apply(Image.new("RGB", (64, 64), (9, 9, 9)))

        def changed(image):
            return ImageChops.difference(image.convert("RGB"), Image.new("RGB", (64, 64), (9, 9, 9))).getbbox()

        box_with, box_without = changed(with_box), changed(without)
        self.assertGreater((box_with[2] - box_with[0]) * (box_with[3] - box_with[1]),
                           (box_without[2] - box_without[0]) * (box_without[3] - box_without[1]))

    def test_a_text_that_is_too_wide_is_cut_to_fit(self):
        result = TextOverlay("This is far too long for the screen", background=None).apply(_black())

        box = _changed_box(result)
        self.assertLessEqual(box[2], 64 - 1)
        self.assertGreaterEqual(box[0], 1)

    def test_the_size_of_the_picture_is_kept_and_the_input_is_not_changed(self):
        original = _black(32)

        result = TextOverlay("x").apply(original)

        self.assertEqual((32, 32), result.size)
        self.assertIsNone(_changed_box(original))

    def test_invalid_values(self):
        for kwargs in ({"text": ""}, {"text": "a", "position": "left"}, {"text": "a", "font_size": 2},
                       {"text": "a", "background": (0, 0, 0)}, {"text": "a", "background": (0, 0, 0, 300)},
                       {"text": "a", "margin": -1}, {"text": "a", "color": "not a color"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    TextOverlay(**kwargs)


class TestOverlayOnMedia(TestBase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        cls.gif = GIFS["flat"](Path(cls._tmp.name) / "flat.gif")
        cls.png = Path(cls._tmp.name) / "black.png"
        _black().save(cls.png)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_text_is_on_every_frame_of_a_gif(self):
        module = GifModule(connection_manager=AsyncMock(), screen_size=ScreenSize.SIZE_64x64)
        overlay = TextOverlay("64c", background=None, color=(255, 255, 255))

        plain = module._load_gif_and_adapt_to_canvas(file_path=self.gif, canvas_size=64, resize_mode=ResizeMode.FILL)
        labeled = module._load_gif_and_adapt_to_canvas(
            file_path=self.gif, canvas_size=64, resize_mode=ResizeMode.FILL, overlay=overlay)

        plain_image, labeled_image = Image.open(io.BytesIO(plain)), Image.open(io.BytesIO(labeled))
        self.assertEqual(plain_image.n_frames, labeled_image.n_frames)
        for frame in range(labeled_image.n_frames):
            plain_image.seek(frame)
            labeled_image.seek(frame)
            difference = ImageChops.difference(plain_image.convert("RGB"), labeled_image.convert("RGB")).getbbox()
            self.assertIsNotNone(difference, f"frame {frame} has no text")
            self.assertLessEqual(difference[0], 4)  # bottom left
            self.assertGreaterEqual(difference[3], 60)

    def test_the_text_is_on_an_image(self):
        pixels = ImageModule._load_image_and_adapt_to_canvas(
            file_path=self.png, canvas_size=64, resize_mode=ResizeMode.FIT, palletize=False,
            background_color=(0, 0, 0), overlay=TextOverlay("hi", position="top-left", background=None))

        result = Image.frombytes("RGB", (64, 64), bytes(pixels))
        box = _changed_box(result)
        self.assertIsNotNone(box)
        self.assertLessEqual(box[0], 2)
        self.assertLessEqual(box[1], 2)

    async def test_store_labels_each_file_with_what_a_function_returns(self):
        # GIVEN
        connection_manager = AsyncMock()
        gif = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        image = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        under_test = MaterialsModule(connection_manager=connection_manager, gif=gif, image=image)
        names = []

        def label(path: str) -> TextOverlay:
            names.append(Path(path).name)
            return TextOverlay(Path(path).stem[:4])

        # WHEN
        await under_test.store([self.png, self.gif], slots=[0, 1], overlay=label)

        # THEN
        self.assertEqual(["black.png", "flat.gif"], names)
        self.assertEqual(2, connection_manager.send_packets.await_count)

    async def test_a_changed_overlay_is_transferred_again(self):
        # GIVEN
        connection_manager = AsyncMock()
        gif = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        image = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        under_test = MaterialsModule(connection_manager=connection_manager, gif=gif, image=image)
        await under_test.store([self.png], slots=[0], overlay=TextOverlay("a"))
        connection_manager.send_packets.reset_mock()

        # WHEN
        await under_test.store([self.png], slots=[0], overlay=TextOverlay("a"))
        same = connection_manager.send_packets.await_count
        await under_test.store([self.png], slots=[0], overlay=TextOverlay("b"))

        # THEN
        self.assertEqual(0, same)
        self.assertEqual(1, connection_manager.send_packets.await_count)
