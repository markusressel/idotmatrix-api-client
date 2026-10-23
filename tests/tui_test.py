import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock

from PIL import Image

from idotmatrix.screensize import ScreenSize
from tests import TestBase

try:
    import textual  # noqa: F401
    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False

from idotmatrix.tui import convert
from idotmatrix.tui.files import files_in, list_folder, natural_key
from idotmatrix.tui.settings import Options, Session


def _make_pictures(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 40), (200, 30, 30)).save(folder / "b2.png")
    Image.new("RGB", (40, 80), (30, 200, 30)).save(folder / "b10.jpg")
    frames = [Image.new("RGB", (64, 64), (i * 40, 0, 255 - i * 40)).quantize(256) for i in range(4)]
    frames[0].save(folder / "a.gif", save_all=True, append_images=frames[1:], duration=[100, 200, 100, 200], loop=0)
    (folder / "notes.txt").write_text("not a picture")
    (folder / ".hidden.png").write_bytes(b"")


class TestSettings(TestBase):

    def test_the_session_is_saved_and_loaded(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "a" / "session.json"
            session = Session(folder="/x", address="AA:BB", slots=[1, 3], display_time=30, brightness=40,
                              options=Options(colors="64", max_size_kb=80, label="text", label_text="hi"))

            session.save(path)
            loaded = Session.load(path)

            self.assertEqual(session, loaded)

    def test_a_missing_or_broken_session_gives_the_defaults(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            self.assertEqual(Session(), Session.load(path))
            path.write_text("{ not json")
            self.assertEqual(Session(), Session.load(path))

    def test_invalid_values_in_the_session_are_replaced(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            path.write_text(json.dumps({
                "slots": [99, "a", 2], "display_time": -4, "brightness": 1000,
                "options": {"colors": "7", "max_size_kb": 0, "resize_mode": "x", "label": "?", "label_position": "?",
                            "unknown": 1}}))

            loaded = Session.load(path)

            self.assertEqual([2], loaded.slots)
            self.assertEqual(10, loaded.display_time)
            self.assertEqual(100, loaded.brightness)
            self.assertEqual(Options(), loaded.options)

    def test_options_give_the_arguments_of_an_upload(self):
        options = Options(colors="32", resize_mode="fit", label="name", label_position="top-right")

        self.assertEqual(32, options.colors_value)
        self.assertEqual("auto", Options().colors_value)
        self.assertEqual("FIT", options.resize.name)
        self.assertEqual("pic", options.overlay_for("/some/pic.gif").text)
        self.assertIsNone(Options().overlay_for("pic.gif"))
        self.assertEqual("hello", Options(label="text", label_text="hello").overlay_for("pic.gif").text)


class TestFiles(TestBase):

    def test_folders_come_first_and_names_are_in_natural_order(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))
            (Path(tmp) / "zdir").mkdir()

            entries = list_folder(Path(tmp))

            self.assertEqual(["zdir/", "a.gif", "b2.png", "b10.jpg"], [entry.name for entry in entries])

    def test_the_filter_matches_part_of_the_name_without_case(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))

            self.assertEqual(["b2.png", "b10.jpg"], [e.name for e in list_folder(Path(tmp), "B")])

    def test_hidden_files_can_be_shown(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))

            self.assertIn(".hidden.png", [e.name for e in list_folder(Path(tmp), show_hidden=True)])

    def test_files_below_a_folder(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))
            _make_pictures(Path(tmp) / "sub")

            self.assertEqual(3, len(files_in(Path(tmp))))
            self.assertEqual(6, len(files_in(Path(tmp), recursive=True)))

    def test_a_missing_folder_is_empty(self):
        self.assertEqual([], list_folder(Path("/does/not/exist")))

    def test_natural_key(self):
        self.assertEqual(["a2", "a10"], sorted(["a10", "a2"], key=natural_key))


class TestConvert(TestBase):

    def test_an_animation_keeps_its_frames_and_delays(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))

            preview = convert.convert(Path(tmp) / "a.gif", 64, Options(colors="256"))

            self.assertTrue(preview.animated)
            self.assertEqual(4, len(preview.frames))
            self.assertEqual([100, 200, 100, 200], preview.durations)
            self.assertEqual((64, 64), preview.frames[0].size)
            self.assertAlmostEqual(0.6, preview.loop_seconds)
            self.assertGreater(preview.size_bytes, 0)

    def test_a_picture_is_one_frame_of_the_screen_size(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))

            preview = convert.convert(Path(tmp) / "b2.png", 32, Options())

            self.assertFalse(preview.animated)
            self.assertEqual(1, len(preview.frames))
            self.assertEqual((32, 32), preview.frames[0].size)

    def test_the_label_is_drawn(self):
        with TemporaryDirectory() as tmp:
            _make_pictures(Path(tmp))

            plain = convert.convert(Path(tmp) / "b2.png", 64, Options())
            labelled = convert.convert(
                Path(tmp) / "b2.png", 64, Options(label="text", label_text="X", label_position="top-left"))

            self.assertNotEqual(plain.frames[0].tobytes(), labelled.frames[0].tobytes())


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestRender(TestBase):

    def test_two_pixels_share_a_cell(self):
        from idotmatrix.tui.preview import render_frame
        image = Image.new("RGB", (4, 4), (255, 0, 0))
        image.putpixel((0, 1), (0, 0, 255))

        text = render_frame(image, 80, 24)

        self.assertEqual(2, len(text.plain.splitlines()))
        self.assertEqual(4, len(text.plain.splitlines()[0]))
        first = text.spans[0].style
        self.assertEqual("rgb(255,0,0)", first.color.name)
        self.assertEqual("rgb(0,0,255)", first.bgcolor.name)

    def test_a_large_picture_is_scaled_down_to_the_space(self):
        from idotmatrix.tui.preview import render_frame

        text = render_frame(Image.new("RGB", (64, 64), (1, 2, 3)), 20, 5)

        lines = text.plain.splitlines()
        self.assertEqual(5, len(lines))
        self.assertEqual(10, len(lines[0]))


class FakeClient:
    """Stands in for `IDotMatrixClient`, the modules record what is called."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.screen_size = ScreenSize.SIZE_64x64
        self.connect = AsyncMock(side_effect=RuntimeError("no display found") if fail else None)
        self.disconnect = AsyncMock()
        self.set_brightness = AsyncMock()
        self.gif = MagicMock(upload_gif_file=AsyncMock())
        self.image = MagicMock(show_image_file=AsyncMock())
        self.clock = MagicMock(show=AsyncMock())
        self.materials = MagicMock(store=AsyncMock(return_value=[0, 1]), clear=AsyncMock())


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestApp(TestBase):

    def setUp(self):
        super().setUp()
        self._tmp = TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "pictures"
        _make_pictures(self.folder)
        self.session_path = Path(self._tmp.name) / "session.json"
        self.client = FakeClient()

    def tearDown(self):
        self._tmp.cleanup()

    def _app(self, client=None):
        from idotmatrix.tui.app import IDotMatrixApp
        client = client or self.client
        return IDotMatrixApp(folder=self.folder, address="AA:BB:CC:DD:EE:FF", client_factory=lambda address: client,
                             session_path=self.session_path)

    async def _settle(self, pilot):
        await pilot.pause()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

    def _rows(self, app):
        from textual.widgets import DataTable
        return [key.value for key in app.query_one("#files", DataTable).rows]

    async def test_lists_the_folder_and_connects(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            self.assertEqual("connected", app.connection)
            self.assertEqual(64, app.canvas_size)
            self.client.connect.assert_awaited_once()
            self.assertEqual(
                ["..", str(self.folder / "a.gif"), str(self.folder / "b2.png"), str(self.folder / "b10.jpg")],
                self._rows(app))

    async def test_a_failed_connection_is_shown_and_nothing_is_sent(self):
        client = FakeClient(fail=True)
        app = self._app(client)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("down", "down", "enter")
            await self._settle(pilot)

            self.assertEqual("failed", app.connection)
            client.image.show_image_file.assert_not_awaited()

    async def test_enter_shows_a_picture_on_the_display(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down", "down", "enter")  # .., a.gif, b2.png
            await self._settle(pilot)

            self.client.image.show_image_file.assert_awaited_once()
            self.assertEqual(self.folder / "b2.png", self.client.image.show_image_file.await_args.args[0])
            self.client.gif.upload_gif_file.assert_not_awaited()

    async def test_enter_shows_an_animation_with_the_options(self):
        app = self._app()
        app.session.options = Options(colors="64", max_size_kb=50)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down", "enter")
            await self._settle(pilot)

            kwargs = self.client.gif.upload_gif_file.await_args.kwargs
            self.assertEqual(self.folder / "a.gif", self.client.gif.upload_gif_file.await_args.args[0])
            self.assertEqual(64, kwargs["colors"])
            self.assertEqual(50, kwargs["max_size_kb"])

    async def test_the_progress_of_an_upload_is_shown(self):
        from textual.widgets import ProgressBar
        seen = []

        async def upload(*args, **kwargs):
            kwargs["progress"](3, 8)
            bar = app.query_one("#progress", ProgressBar)
            seen.append((bar.display, bar.progress, bar.total))

        self.client.gif.upload_gif_file.side_effect = upload
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("down", "enter")
            await self._settle(pilot)

            self.assertEqual([(True, 3, 8)], seen)
            self.assertFalse(app.query_one("#progress", ProgressBar).display)

    async def test_enter_on_a_folder_opens_it_and_backspace_goes_up(self):
        sub = self.folder / "sub"
        _make_pictures(sub)
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down", "enter")  # .., sub/
            self.assertEqual(sub, app.folder)
            await pilot.press("backspace")

            self.assertEqual(self.folder, app.folder)
            self.client.image.show_image_file.assert_not_awaited()

    async def test_space_marks_and_s_stores_the_marked_files_in_the_chosen_slots(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("down", "space", "space")  # a.gif and b2.png
            self.assertEqual([self.folder / "a.gif", self.folder / "b2.png"], app.marked)

            await pilot.press("s")
            await pilot.pause()
            await pilot.click("#ok")
            await self._settle(pilot)

            args = self.client.materials.store.await_args
            self.assertEqual([str(self.folder / "a.gif"), str(self.folder / "b2.png")], args.args[0])
            self.assertEqual(list(range(12)), args.kwargs["slots"])
            self.assertEqual(10, args.kwargs["display_time"])
            self.assertEqual("auto", args.kwargs["colors"])

    async def test_without_marks_s_stores_the_whole_folder(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("s")
            await pilot.pause()
            await pilot.click("#ok")
            await self._settle(pilot)

            self.assertEqual(3, len(self.client.materials.store.await_args.args[0]))

    async def test_store_labels_the_files_with_the_label_option(self):
        app = self._app()
        app.session.options = Options(label="name")
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("s")
            await pilot.pause()
            await pilot.click("#ok")
            await self._settle(pilot)

            overlay = self.client.materials.store.await_args.kwargs["overlay"]
            self.assertEqual("b2", overlay("/x/b2.png").text)

    async def test_more_files_than_slots_is_refused_in_the_dialog(self):
        app = self._app()
        app.session.slots = [4]
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("s")
            await pilot.pause()
            await pilot.click("#ok")
            await self._settle(pilot)

            self.client.materials.store.assert_not_awaited()
            self.assertEqual("SlideshowDialog", type(app.screen).__name__)

    async def test_the_options_are_changed_and_remembered(self):
        from textual.widgets import Input, Select
        app = self._app()
        async with app.run_test(size=(120, 50)) as pilot:
            await self._settle(pilot)
            await pilot.press("o")
            await pilot.pause()
            app.screen.query_one("#colors", Select).value = "32"
            app.screen.query_one("#max_size", Input).value = "70"
            await pilot.click("#ok")
            await self._settle(pilot)

            self.assertEqual(32, app.session.options.colors_value)
            self.assertEqual(70, app.session.options.max_size_kb)
        self.assertEqual("32", json.loads(self.session_path.read_text())["options"]["colors"])

    async def test_brightness_clock_and_clear(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("c")
            await self._settle(pilot)
            self.client.clock.show.assert_awaited_once()

            await pilot.press("b")
            await pilot.pause()
            app.screen.query_one("#number").value = "40"
            await pilot.click("#ok")
            await self._settle(pilot)
            self.client.set_brightness.assert_awaited_once_with(40)

            await pilot.press("x")
            await pilot.pause()
            await pilot.click("#ok")
            await self._settle(pilot)
            self.client.materials.clear.assert_awaited_once()

    async def test_a_second_upload_waits_for_the_first(self):
        release = asyncio.Event()

        async def slow(*args, **kwargs):
            await release.wait()

        self.client.image.show_image_file.side_effect = slow
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("down", "down", "enter")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()

            self.client.clock.show.assert_not_awaited()
            release.set()
            await self._settle(pilot)

    async def test_escape_cancels_the_running_upload(self):
        started = asyncio.Event()

        async def hang(*args, **kwargs):
            started.set()
            await asyncio.sleep(60)

        self.client.image.show_image_file.side_effect = hang
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("down", "down", "enter")
            await started.wait()

            await pilot.press("escape")
            await self._settle(pilot)

            self.assertIsNone(app._busy)

    async def test_the_filter_narrows_the_list(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("slash", "b", "1")

            self.assertEqual(["..", str(self.folder / "b10.jpg")], self._rows(app))
            await pilot.press("escape")
            self.assertEqual(4, len(self._rows(app)))

    async def test_the_folder_is_remembered(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

        self.assertEqual(str(self.folder), json.loads(self.session_path.read_text())["folder"])
        self.client.disconnect.assert_awaited()

    async def test_the_preview_shows_what_will_be_sent(self):
        from idotmatrix.tui.preview import PreviewWidget
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down")
            await pilot.pause(0.5)
            await self._settle(pilot)

            self.assertEqual(4, len(app._preview.frames))
            self.assertGreater(len(app.query_one(PreviewWidget)._frames), 1)
            self.assertIn("4 frames", str(app.query_one("#info").render()))
