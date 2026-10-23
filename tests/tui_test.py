import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

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
from idotmatrix.tui.scanner import Found
from idotmatrix.tui.settings import KnownDevice, Options, Session


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

    def test_taller_cells_make_the_picture_wider_so_it_stays_square(self):
        from idotmatrix.tui.preview import render_frame

        text = render_frame(Image.new("RGB", (10, 10), (1, 2, 3)), 80, 24, aspect=2.4)

        lines = text.plain.splitlines()
        self.assertEqual(5, len(lines))
        self.assertEqual(12, len(lines[0]))  # 10 pixels, each 1.2 cells wide


class FakeScanner:
    """Finds the given displays, right away."""

    def __init__(self, found=None, error=None):
        self.found = found or []
        self.error = error
        self.scans = 0

    async def scan(self, seconds):
        self.scans += 1
        await asyncio.sleep(0.01)
        if self.error:
            raise self.error
        return list(self.found)


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


class AppHelpers:
    """What the tests of the app share."""

    def setUp(self):
        super().setUp()
        self._tmp = TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "pictures"
        _make_pictures(self.folder)
        self.session_path = Path(self._tmp.name) / "session.json"
        self.client = FakeClient()

    def tearDown(self):
        self._tmp.cleanup()

    def _app(self, client=None, address="AA:BB:CC:DD:EE:FF", scanner=None, **kwargs):
        from idotmatrix.tui.app import IDotMatrixApp
        client = client or self.client
        self.addresses = []

        def factory(address):
            self.addresses.append(address)
            return client

        return IDotMatrixApp(folder=self.folder, address=address, client_factory=factory,
                             session_path=self.session_path, scanner=scanner or FakeScanner(), **kwargs)

    async def _settle(self, pilot):
        await pilot.pause()
        # the search of the displays screen never ends
        pending = [worker for worker in pilot.app.workers if worker.group != "scan" and not worker.is_finished]
        await asyncio.gather(*[worker.wait() for worker in pending], return_exceptions=True)
        await pilot.pause()

    def _rows(self, app):
        from textual.widgets import DataTable
        return [key.value for key in app.query_one("#files", DataTable).rows]


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestApp(AppHelpers, TestBase):

    async def test_lists_the_folder_and_connects(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            self.assertEqual("connected", app.connection)
            self.assertEqual(64, app.canvas_size)
            self.client.connect.assert_awaited_once()
            self.assertEqual(
                [str(self.folder / "a.gif"), str(self.folder / "b2.png"), str(self.folder / "b10.jpg")],
                self._rows(app))

    async def test_connecting_is_retried_while_bluez_is_still_busy(self):
        client = FakeClient()
        client.connect = AsyncMock(side_effect=[RuntimeError("[org.bluez.Error.InProgress] Operation already in progress"), None])
        app = self._app(client)
        with patch("idotmatrix.tui.app.CONNECT_RETRY_SECONDS", 0):
            async with app.run_test(size=(120, 40)) as pilot:
                await self._settle(pilot)

                self.assertEqual("connected", app.connection)
                self.assertEqual(2, client.connect.await_count)

    async def test_a_failed_connection_is_shown_and_nothing_is_sent(self):
        client = FakeClient(fail=True)
        app = self._app(client)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("down", "enter")
            await self._settle(pilot)

            self.assertEqual("failed", app.connection)
            client.image.show_image_file.assert_not_awaited()

    async def test_enter_shows_a_picture_on_the_display(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down", "enter")  # a.gif, b2.png
            await self._settle(pilot)

            self.client.image.show_image_file.assert_awaited_once()
            self.assertEqual(self.folder / "b2.png", self.client.image.show_image_file.await_args.args[0])
            self.client.gif.upload_gif_file.assert_not_awaited()

    async def test_enter_shows_an_animation_with_the_options(self):
        app = self._app()
        app.session.options = Options(colors="64", max_size_kb=50)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("enter")
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
            await pilot.press("enter")
            await self._settle(pilot)

            self.assertEqual([(True, 3, 8)], seen)
            self.assertFalse(app.query_one("#progress", ProgressBar).display)

    async def test_enter_on_a_folder_opens_it_and_backspace_goes_up(self):
        sub = self.folder / "sub"
        _make_pictures(sub)
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("enter")  # sub/
            self.assertEqual(sub, app.folder)
            await pilot.press("backspace")

            self.assertEqual(self.folder, app.folder)
            self.client.image.show_image_file.assert_not_awaited()

    async def test_space_marks_and_s_stores_the_marked_files_in_the_chosen_slots(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("space", "space")  # a.gif and b2.png
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
            await pilot.press("down", "enter")
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
            await pilot.press("down", "enter")
            await started.wait()

            await pilot.press("escape")
            await self._settle(pilot)

            self.assertIsNone(app._busy)

    async def test_the_filter_narrows_the_list(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("slash", "b", "1")

            self.assertEqual([str(self.folder / "b10.jpg")], self._rows(app))
            await pilot.press("escape")
            self.assertEqual(3, len(self._rows(app)))

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

            await pilot.pause(0.5)
            await self._settle(pilot)

            self.assertEqual(4, len(app._preview.frames))
            self.assertGreater(len(app.query_one(PreviewWidget)._frames), 1)
            self.assertIn("4 frames", str(app.query_one("#info").render()))


class TestSessionDevices(TestBase):

    def test_remembering_a_device_makes_it_the_next_one(self):
        session = Session()

        session.remember("AA:01", "IDM-1", now=100.0)
        session.remember("AA:02", "IDM-2", now=200.0)
        session.remember("AA:01", now=300.0)

        self.assertEqual("AA:01", session.address)
        self.assertEqual([("AA:01", "IDM-1", 300.0), ("AA:02", "IDM-2", 200.0)],
                         [(d.address, d.name, d.last_connected) for d in session.devices])

    def test_forgetting_the_current_device_clears_the_address(self):
        session = Session()
        session.remember("AA:01")
        session.remember("AA:02")

        session.forget("AA:02")

        self.assertIsNone(session.address)
        self.assertEqual(["AA:01"], [d.address for d in session.devices])

    def test_devices_survive_saving_and_broken_entries_are_dropped(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.json"
            session = Session()
            session.remember("AA:01", "IDM-1", now=5.0)
            session.save(path)
            raw = json.loads(path.read_text())
            raw["devices"] += [{"address": 5}, "x", {"address": "", "name": "a"}, {"address": "AA:03", "name": 4}]
            path.write_text(json.dumps(raw))

            loaded = Session.load(path)

            self.assertEqual([KnownDevice("AA:01", "IDM-1", 5.0), KnownDevice("AA:03", "", None)], loaded.devices)


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestDevices(AppHelpers, TestBase):

    def _shown_rows(self, app):
        from textual.widgets import DataTable
        table = app.screen.query_one("#devices", DataTable)
        return [[str(cell) for cell in table.get_row(key.value)] for key in table.rows]

    async def test_without_an_address_the_displays_are_searched_and_the_chosen_one_is_connected_and_remembered(self):
        scanner = FakeScanner([Found("AA:01", "IDM-weak", -80), Found("AA:02", "IDM-strong", -40)])
        app = self._app(address=None, scanner=scanner)
        app.session.address = None
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)

            self.assertEqual("DevicesScreen", type(app.screen).__name__)
            self.assertEqual([["● online -40 dBm", "IDM-strong", "AA:02", "new"],
                              ["● online -80 dBm", "IDM-weak", "AA:01", "new"]], self._shown_rows(app))
            self.assertEqual([], self.addresses)

            await pilot.press("enter")  # the strongest
            await self._settle(pilot)

            self.assertEqual(["AA:02"], self.addresses)
            self.assertEqual("connected", app.connection)
            self.assertEqual("AA:02", app.session.address)
            self.assertEqual(["IDM-strong"], [d.name for d in app.session.devices])
        self.assertEqual("AA:02", json.loads(self.session_path.read_text())["address"])

    async def test_known_displays_that_do_not_advertise_are_offline(self):
        app = self._app(address="AA:01", scanner=FakeScanner([Found("AA:02", "IDM-2", -50)]))
        app.session.remember("AA:01", "IDM-1", now=1.0)
        app.session.remember("AA:03", "IDM-3", now=2.0)
        app.session.address = "AA:01"
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("d")
            await pilot.pause(0.3)

            rows = self._shown_rows(app)
            self.assertEqual(["● connected", "IDM-1", "AA:01"], rows[0][:3])
            self.assertEqual(["● online -50 dBm", "IDM-2", "AA:02", "new"], rows[1])
            self.assertEqual({"○ offline"}, {row[0] for row in rows[2:]})
            self.assertEqual(["AA:03"], [row[2] for row in rows[2:]])

    async def test_choosing_another_display_connects_to_it(self):
        scanner = FakeScanner([Found("AA:02", "IDM-2", -50)])
        app = self._app(address="AA:01", scanner=scanner)
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("d")
            await pilot.pause(0.3)

            await pilot.press("down", "enter")  # the connected one is first
            await self._settle(pilot)

            self.assertEqual(["AA:01", "AA:02"], self.addresses)
            self.assertEqual("AA:02", app.session.address)

    async def test_a_failed_connection_opens_the_list_of_displays(self):
        app = self._app(client=FakeClient(fail=True), scanner=FakeScanner())
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)

            self.assertEqual("DevicesScreen", type(app.screen).__name__)

    async def test_choose_opens_the_list_instead_of_connecting(self):
        app = self._app(address="AA:01", scanner=FakeScanner(), choose_device=True)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)

            self.assertEqual("DevicesScreen", type(app.screen).__name__)
            self.assertEqual([], self.addresses)

    async def test_a_display_can_be_forgotten(self):
        app = self._app(address="AA:01", scanner=FakeScanner())
        app.session.remember("AA:05", "IDM-5", now=1.0)
        app.session.address = "AA:01"
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("d")
            await pilot.pause(0.3)
            await pilot.press("down", "f")  # AA:01 is connected, AA:05 is offline

            self.assertEqual([], [d.address for d in app.session.devices if d.address == "AA:05"])
            self.assertEqual(["AA:01"], [row[2] for row in self._shown_rows(app)])

    async def test_an_address_can_be_typed(self):
        app = self._app(address=None, scanner=FakeScanner())
        app.session.address = None
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)

            await pilot.press("a", *"11:22:33:44:55:66", "enter")
            await self._settle(pilot)

            self.assertEqual(["11:22:33:44:55:66"], self.addresses)

    async def test_a_failing_scan_is_shown(self):
        from textual.widgets import Label
        app = self._app(address=None, scanner=FakeScanner(error=RuntimeError("bluetooth is off")))
        app.session.address = None
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause(0.3)

            self.assertIn("bluetooth is off", str(app.screen.query_one("#scan-state", Label).render()))


class TestAgo(TestBase):

    def test_format_ago(self):
        from idotmatrix.tui.devices import format_ago
        self.assertEqual("never", format_ago(None, 100))
        self.assertEqual("just now", format_ago(80, 100))
        self.assertEqual("5 min ago", format_ago(0, 300))
        self.assertEqual("2 h ago", format_ago(0, 7300))
        self.assertEqual("3 d ago", format_ago(0, 3 * 86400 + 5))


class TestJpegWithSeveralPictures(TestBase):

    def test_a_jpeg_with_several_pictures_is_not_an_animation(self):
        # GIVEN a phone style MPO file: a JPEG that holds more than one picture
        import io
        buffer = io.BytesIO()
        first = Image.new("RGB", (40, 40), (200, 0, 0))
        first.save(buffer, "MPO", save_all=True, append_images=[Image.new("RGB", (40, 40), (0, 0, 200))])
        path = Path(TemporaryDirectory().name + ".jpg")
        path.write_bytes(buffer.getvalue())
        try:
            # WHEN / THEN
            self.assertGreater(Image.open(path).n_frames, 1)
            self.assertFalse(convert.is_animated(path))
            self.assertEqual(1, len(convert.convert(path, 64, Options()).frames))
        finally:
            path.unlink()


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestBrowsing(AppHelpers, TestBase):

    def _make_folders(self):
        from textual.widgets import DataTable, Input  # noqa: F401
        for name in ("one", "two"):
            _make_pictures(self.folder / name)

    async def test_right_enters_the_selected_folder_and_left_goes_up_with_the_folder_selected(self):
        self._make_folders()
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down", "right")
            self.assertEqual(self.folder / "two", app.folder)
            await pilot.press("left")
            await self._settle(pilot)

            self.assertEqual(self.folder, app.folder)
            self.assertEqual(self.folder / "two", app.selected_path())

    async def test_right_on_a_file_does_nothing_and_alt_up_goes_up(self):
        self._make_folders()
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("down", "down", "right")
            self.assertEqual(self.folder, app.folder)
            await pilot.press("alt+up")

            self.assertEqual(self.folder.parent, app.folder)

    async def test_the_selection_of_a_folder_is_remembered_when_coming_back(self):
        self._make_folders()
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("right", "down", "down")  # one/: a.gif, b2.png
            selected = app.selected_path()
            await pilot.press("left", "down", "right")  # two/
            await pilot.press("left", "up", "right")  # one/ again
            await self._settle(pilot)

            self.assertEqual(selected, app.selected_path())

    async def test_the_selections_are_remembered_between_runs(self):
        self._make_folders()
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("right", "down")
            selected = app.selected_path()
            await pilot.press("left")
            await self._settle(pilot)

        again = self._app()
        async with again.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("right")
            await self._settle(pilot)

            self.assertEqual(selected, again.selected_path())

    async def test_a_selection_that_is_gone_moves_to_the_row_it_was_on(self):
        self._make_folders()
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)
            await pilot.press("right", "down", "down")
            (self.folder / "one" / "b2.png").unlink()
            await pilot.press("left", "right")
            await self._settle(pilot)

            self.assertEqual(self.folder / "one" / "b10.jpg", app.selected_path())

    async def test_long_names_are_shortened_so_the_list_does_not_scroll_sideways(self):
        from textual.widgets import DataTable, Input  # noqa: F401
        long_name = "a" * 120 + ".png"
        Image.new("RGB", (8, 8)).save(self.folder / long_name)
        app = self._app()
        async with app.run_test(size=(70, 30)) as pilot:
            await self._settle(pilot)
            await pilot.pause(0.2)

            table = app.query_one("#files", DataTable)
            self.assertEqual(0, table.max_scroll_x)
            names = [table.get_row_at(row)[1] for row in range(table.row_count)]
            self.assertTrue(any(name.endswith(".png") and "…" in name for name in names))

    async def test_up_and_down_move_through_the_list_while_the_filter_is_typed(self):
        from textual.widgets import DataTable, Input  # noqa: F401
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("slash", "down")
            self.assertEqual(self.folder / "b2.png", app.selected_path())
            await pilot.press("backspace")  # nothing typed: leaves the filter
            self.assertFalse(app.query_one("#filter", Input).has_class("visible"))

    async def test_shift_down_marks_the_files_it_passes(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("shift+down", "shift+down")

            self.assertEqual([self.folder / "a.gif", self.folder / "b2.png", self.folder / "b10.jpg"], app.marked)

    async def test_messages_are_shown_in_the_status_bar_not_as_popups(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            app.notify("Something happened", severity="warning")
            await pilot.pause()

            self.assertIn("Something happened", str(app.query_one("#message").render()))
            self.assertEqual(0, len(app._notifications))


class TestParsePath(TestBase):

    def setUp(self):
        super().setUp()
        self._tmp = TemporaryDirectory()
        self.base = Path(self._tmp.name)
        (self.base / "sub").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_pasted_forms_of_a_path_are_understood(self):
        from idotmatrix.tui.dialogs import parse_path
        sub = self.base / "sub"

        for text in (f" {sub} ", f"'{sub}'", f'"{sub}"', f"file://{sub}", "sub", "./sub/", "sub/../sub"):
            with self.subTest(text=text):
                self.assertEqual(sub, parse_path(text, self.base))

    def test_home_is_expanded(self):
        from idotmatrix.tui.dialogs import parse_path

        self.assertEqual(Path.home(), parse_path("~", self.base))

    def test_a_missing_path_or_nothing_is_rejected(self):
        from idotmatrix.tui.dialogs import parse_path

        for text in ("", "  ", "nothing-here"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_path(text, self.base)


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestGoTo(AppHelpers, TestBase):

    async def test_g_opens_a_dialog_and_enter_goes_to_the_pasted_folder(self):
        from textual.widgets import Input
        target = self.folder / "sub"
        _make_pictures(target)
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("g")
            field = app.screen.query_one("#path", Input)
            field.value = f"'{target}'"
            await pilot.press("enter")
            await self._settle(pilot)

            self.assertEqual(target, app.folder)

    async def test_a_file_opens_its_folder_with_the_file_selected(self):
        from textual.widgets import Input
        target = self.folder / "sub"
        _make_pictures(target)
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("g")
            app.screen.query_one("#path", Input).value = str(target / "b2.png")
            await pilot.press("enter")
            await self._settle(pilot)

            self.assertEqual(target, app.folder)
            self.assertEqual(target / "b2.png", app.selected_path())

    async def test_a_wrong_path_keeps_the_dialog_open(self):
        from textual.widgets import Input
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("g")
            app.screen.query_one("#path", Input).value = str(self.folder / "missing")
            await pilot.press("enter")

            self.assertEqual(self.folder, app.folder)
            self.assertIsNotNone(app.screen.query("#path").first())


@unittest.skipUnless(HAS_TEXTUAL, "needs textual")
class TestListKeys(AppHelpers, TestBase):

    async def test_home_and_end_select_the_first_and_last_entry(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            await pilot.press("end")
            self.assertEqual(self.folder / "b10.jpg", app.selected_path())
            await pilot.press("home")
            self.assertEqual(self.folder / "a.gif", app.selected_path())

    async def test_page_keys_move_by_the_rows_shown_and_stop_at_the_ends(self):
        from textual.widgets import DataTable
        for number in range(40):
            Image.new("RGB", (4, 4)).save(self.folder / f"x{number:02}.png")
        app = self._app()
        async with app.run_test(size=(120, 20)) as pilot:
            await self._settle(pilot)
            table = app.query_one("#files", DataTable)
            page = table.scrollable_content_region.height - 1

            await pilot.press("pagedown")
            self.assertEqual(page, table.cursor_row)
            await pilot.press("pageup", "pageup")
            self.assertEqual(0, table.cursor_row)

    async def test_the_circle_of_the_connection_is_colored(self):
        app = self._app()
        async with app.run_test(size=(120, 40)) as pilot:
            await self._settle(pilot)

            text = app.query_one("#status").render()
            circle = next(span for span in text.spans if text.plain[span.start:span.end] == "●")
            self.assertIn("green", str(circle.style))
