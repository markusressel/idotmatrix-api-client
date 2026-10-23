import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from tests import TestBase
from tests.tui_test import HAS_TEXTUAL, AppHelpers

from idotmatrix.tui.canvas import PixelCanvas
from idotmatrix.tui.features import FEATURES
from idotmatrix.tui.forms import Feature, Field
from idotmatrix.tui.settings import Options, Session

RED = (255, 0, 0)
BLUE = (0, 0, 255)
BLACK = (0, 0, 0)


class TestPixelCanvas(TestBase):

    def test_a_change_is_remembered_once_until_it_is_taken(self):
        canvas = PixelCanvas(8)

        canvas.set(1, 2, RED)
        canvas.set(1, 2, RED)
        canvas.set(3, 3, BLUE)

        self.assertEqual({(1, 2): RED, (3, 3): BLUE}, canvas.take_dirty())
        self.assertEqual({}, canvas.take_dirty())

    def test_a_line_and_a_box(self):
        canvas = PixelCanvas(8)

        canvas.line(0, 0, 3, 3, RED)
        canvas.rectangle(4, 4, 6, 6, BLUE)

        self.assertTrue(all(canvas.get(i, i) == RED for i in range(4)))
        self.assertEqual(BLUE, canvas.get(5, 4))
        self.assertEqual(BLACK, canvas.get(5, 5))  # only the outline

    def test_fill_stops_at_other_colors(self):
        canvas = PixelCanvas(4)
        canvas.line(2, 0, 2, 3, BLUE)

        canvas.fill(0, 0, RED)

        self.assertEqual(RED, canvas.get(1, 3))
        self.assertEqual(BLACK, canvas.get(3, 0))

    def test_undo_and_redo_restore_the_picture_and_mark_it_for_sending(self):
        canvas = PixelCanvas(4)
        canvas.begin()
        canvas.set(0, 0, RED)
        canvas.take_dirty()

        self.assertTrue(canvas.undo())
        self.assertEqual(BLACK, canvas.get(0, 0))
        self.assertEqual({(0, 0): BLACK}, canvas.take_dirty())
        self.assertTrue(canvas.redo())
        self.assertEqual(RED, canvas.get(0, 0))
        self.assertFalse(canvas.redo())

    def test_a_picture_is_scaled_without_smoothing(self):
        canvas = PixelCanvas(4)
        image = Image.new("RGB", (2, 2), RED)
        image.putpixel((1, 1), BLUE)

        canvas.load(image)

        self.assertEqual(BLUE, canvas.get(3, 3))
        self.assertEqual(BLUE, canvas.get(2, 2))
        self.assertEqual(RED, canvas.get(1, 1))


class TestFeatures(TestBase):

    def test_every_feature_accepts_its_defaults(self):
        for feature in FEATURES:
            with self.subTest(feature=feature.id):
                feature.check(feature.defaults())

    def test_saved_values_are_used_if_they_still_fit(self):
        feature = Feature("f", "F", "", fields=(Field("n", "N", "int", 5, low=0, high=9),
                                                Field("c", "C", "choice", 1, choices=(("a", 1), ("b", 2)))))

        values = feature.restore({"n": 7, "c": 3})

        self.assertEqual({"n": 7, "c": 1}, values)

    def test_wrong_input_is_explained(self):
        feature = Feature("f", "F", "", fields=(
            Field("n", "Minutes", "int", 5, low=0, high=59), Field("c", "Color", "color", "#fff"),
            Field("t", "From", "time", "22:00")))

        for key, value, message in (("n", "99", "from 0 to 59"), ("n", "x", "number"), ("c", "nope", "not a color"),
                                    ("t", "25:00", "hours and minutes")):
            with self.subTest(key=key, value=value):
                raw = feature.defaults() | {key: value}
                with self.assertRaises(ValueError) as error:
                    feature.check(raw)
                self.assertIn(message, str(error.exception))


class TestSessionOptions(TestBase):

    def test_the_new_options_are_kept_and_bad_ones_are_dropped(self):
        options = Options(image_format="raw", palette="on", shared_palette=True, max_color_error=9.5,
                          background="#112233")
        broken = Options(image_format="jpeg", palette="maybe", shared_palette="yes", max_color_error=500,
                         background="nonsense")

        self.assertEqual(("raw", "on", True, 9.5, "#112233"), (
            options.image_format, options.palette, options.shared_palette, options.max_color_error,
            options.background))
        self.assertEqual(("png", "auto", False, 5.0, "#000000"), (
            broken.image_format, broken.palette, broken.shared_palette, broken.max_color_error, broken.background))
        self.assertFalse(options.png)
        self.assertTrue(options.palletize_for(False))
        self.assertFalse(Options().palletize_for(False))
        self.assertTrue(Options().palletize_for(True))

    def test_the_values_of_the_controls_are_saved(self):
        import tempfile
        from pathlib import Path
        session = Session()
        session.controls["clock"] = {"style": 3}
        session.draw_color = "#00ff00"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.json"
            session.save(path)

            loaded = Session.load(path)

        self.assertEqual({"clock": {"style": 3}}, loaded.controls)
        self.assertEqual("#00ff00", loaded.draw_color)


def _device_client(client):
    for name in ("clock", "text", "color", "effect", "common", "countdown", "chronograph", "scoreboard", "eco",
                 "music_sync", "system", "graffiti"):
        setattr(client, name, MagicMock())
    for module, methods in {
        "clock": ("show",), "text": ("show_text",), "color": ("show_color",), "effect": ("show",),
        "common": ("set_brightness", "turn_on", "turn_off", "set_screen_flipped", "set_time", "get_device_info",
                   "reset"),
        "countdown": ("start", "pause", "restart", "stop"),
        "chronograph": ("start_from_zero", "pause", "resume", "reset"), "scoreboard": ("show",), "eco": ("set_mode",),
        "music_sync": ("set_mic_type",), "system": ("delete_device_data",), "graffiti": ("set_pixels",),
    }.items():
        for method in methods:
            setattr(getattr(client, module), method, AsyncMock())
    client.image.set_mode = AsyncMock()
    client.image.show_image_pixeldata = AsyncMock()


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestPages(AppHelpers, TestBase):

    def setUp(self):
        super().setUp()
        _device_client(self.client)

    async def test_the_function_keys_switch_between_the_pages(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("f2")
            self.assertEqual("controls", app.screen.page_id)
            await pilot.press("f3")
            self.assertEqual("draw", app.screen.page_id)
            await pilot.press("f2")
            self.assertEqual("controls", app.screen.page_id)
            await pilot.press("f1")
            self.assertIs(app.main_screen, app.screen)

    async def test_the_keys_of_the_files_do_nothing_on_the_other_pages(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("f2")

            await pilot.press("s", "o")

            self.assertEqual("controls", app.screen.page_id)
            self.client.materials.store.assert_not_awaited()

    async def test_a_button_runs_its_feature_with_the_checked_values(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("f2")
            await pilot.pause()

            await pilot.click("#clock-action0")
            await self._until(pilot, lambda: self.client.clock.show.await_count)

            self.client.clock.show.assert_awaited_once_with(
                style=0, show_date=True, hour24=True, color=(255, 255, 255))
            self.assertEqual(0, app.session.controls["clock"]["style"])

    async def test_a_wrong_value_is_reported_and_nothing_is_sent(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("f2", "down", "down", "down", "down", "down")  # countdown
            await pilot.pause()
            app.screen.query_one("#countdown-minutes").value = "99"

            await pilot.click("#countdown-action0")
            await pilot.pause()

            self.client.countdown.start.assert_not_awaited()
            self.assertIn("from 0 to 59", str(app.message_text))

    async def test_drawing_sends_the_pixels_to_the_display_in_the_draw_mode(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("f3")
            await pilot.pause()

            await pilot.press("1", "space")
            await self._until(pilot, lambda: self.client.graffiti.set_pixels.await_count > 1)

            self.client.image.set_mode.assert_awaited_once()
            sent = {}
            for call in self.client.graffiti.set_pixels.await_args_list:
                sent.setdefault(call.args[0], []).extend(call.args[1])
            self.assertIn((32, 32), sent[(255, 0, 0)])  # the cursor starts in the middle
            self.assertEqual(64 * 64 - 1, len(sent[(0, 0, 0)]))
