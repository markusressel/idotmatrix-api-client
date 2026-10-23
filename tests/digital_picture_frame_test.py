import asyncio
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from idotmatrix.apps.digital_picture_frame import DigitalPictureFrame, PictureFrameGif, PictureFrameImage
from tests import TestBase


def _client() -> MagicMock:
    client = MagicMock()
    for path in (
        "image.show_image_file", "gif.upload_gif_file",
        "color.show_color", "clock.show", "reset", "disconnect",
    ):
        obj = client
        *parents, name = path.split(".")
        for parent in parents:
            obj = getattr(obj, parent)
        setattr(obj, name, AsyncMock())
    return client


async def _eventually(condition, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        await asyncio.sleep(0.05)
    return condition()


class DigitalPictureFrameTestBase(TestBase):

    def setUp(self):
        self.client = _client()
        self.frame = DigitalPictureFrame(device_client=self.client)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        real_sleep = asyncio.sleep

        async def short_sleep(_seconds):
            # must still yield to the event loop, or the slideshow loop would starve everything else
            await real_sleep(0.01)

        sleep_patcher = patch("idotmatrix.apps.digital_picture_frame.sleep", new=short_sleep)
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)
        self.addCleanup(self._stop_observers)

    def _stop_observers(self):
        for observer in self.frame._filesystem_observers:
            observer.stop()
            observer.join(timeout=2)

    def _touch(self, relative: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        return path

    def _paths(self) -> set[Path]:
        return {Path(image.file_path) for image in self.frame.images}


class TestImageList(DigitalPictureFrameTestBase):

    def test_registers_a_connection_listener(self):
        self.client.add_connection_listener.assert_called_once()
        self.client.set_auto_reconnect.assert_called_once_with(True)
        # unattended, so a connection that died silently has to be noticed
        self.client.set_heartbeat.assert_called_once_with(60)

    def test_add_and_remove_image(self):
        self.frame.add_image("a.png")
        self.frame.add_image(PictureFrameImage(Path("b.png")))

        self.frame.remove_image(Path("b.png"))
        self.frame.remove_image("not-in-list.png")

        self.assertEqual(["a.png"], self.frame.images)

    def test_add_image_rejects_wrong_type(self):
        with self.assertRaises(ValueError):
            self.frame.add_image(42)

    def test_add_folder_adds_supported_files_only(self):
        self._touch("a.png")
        self._touch("b.JPG")
        self._touch("c.gif")
        self._touch("notes.txt")

        self.frame.add_folder(self.root)

        self.assertEqual({self.root / "a.png", self.root / "b.JPG", self.root / "c.gif"}, self._paths())
        kinds = {Path(i.file_path).name: type(i) for i in self.frame.images}
        self.assertIs(PictureFrameGif, kinds["c.gif"])
        self.assertIs(PictureFrameImage, kinds["a.png"])

    def test_add_folder_is_not_recursive_by_default(self):
        self._touch("a.png")
        self._touch("sub/b.png")

        self.frame.add_folder(self.root)

        self.assertEqual({self.root / "a.png"}, self._paths())

    def test_add_folder_recursive(self):
        self._touch("a.png")
        self._touch("sub/deeper/b.png")

        self.frame.add_folder(self.root, recursive=True)

        self.assertEqual({self.root / "a.png", self.root / "sub/deeper/b.png"}, self._paths())

    def test_add_folder_rejects_non_directories(self):
        with self.assertRaises(ValueError):
            self.frame.add_folder(self.root / "missing")

    def test_set_interval(self):
        self.frame.set_interval(7)
        self.assertEqual(7, self.frame.interval_seconds)

    def test_set_interval_rejects_non_positive(self):
        with self.assertRaises(ValueError):
            self.frame.set_interval(0)


class TestFolderWatch(DigitalPictureFrameTestBase):

    async def test_new_file_is_added(self):
        self.frame.watch_folders([self.root])

        path = self._touch("new.png")

        self.assertTrue(await _eventually(lambda: path in self._paths()))

    async def test_new_file_is_added_exactly_once(self):
        self.frame.watch_folders([self.root], recursive=True)

        self._touch("new.png")
        await _eventually(lambda: len(self.frame.images) > 0)
        await asyncio.sleep(0.5)

        self.assertEqual(1, len(self.frame.images))

    async def test_unsupported_files_are_ignored(self):
        self.frame.watch_folders([self.root])

        self._touch("notes.txt")
        path = self._touch("new.png")

        self.assertTrue(await _eventually(lambda: path in self._paths()))
        self.assertEqual({path}, self._paths())

    async def test_deleted_file_is_removed(self):
        existing = self._touch("old.png")
        self.frame.watch_folders([self.root])
        self.assertEqual({existing}, self._paths())

        existing.unlink()

        self.assertTrue(await _eventually(lambda: not self._paths()))

    async def test_moved_file_is_replaced(self):
        existing = self._touch("old.png")
        self.frame.watch_folders([self.root])

        target = self.root / "renamed.png"
        existing.rename(target)

        self.assertTrue(await _eventually(lambda: self._paths() == {target}))

    async def test_files_in_subfolders_are_ignored_when_not_recursive(self):
        self.frame.watch_folders([self.root], recursive=False)

        self._touch("sub/hidden.png")
        visible = self._touch("visible.png")

        self.assertTrue(await _eventually(lambda: visible in self._paths()))
        await asyncio.sleep(0.3)
        self.assertEqual({visible}, self._paths())

    async def test_files_in_subfolders_are_added_when_recursive(self):
        (self.root / "sub").mkdir()
        self.frame.watch_folders([self.root], recursive=True)

        nested = self._touch("sub/nested.png")

        self.assertTrue(await _eventually(lambda: nested in self._paths()))

    async def test_files_in_folders_created_later_are_added_when_recursive(self):
        self.frame.watch_folders([self.root], recursive=True)

        nested = self._touch("later/nested.png")

        self.assertTrue(await _eventually(lambda: nested in self._paths()))


class TestSlideshow(DigitalPictureFrameTestBase):

    async def test_next_shows_a_png(self):
        self.frame.add_image(PictureFrameImage(Path("a.png")))

        await self.frame.next()

        self.client.image.show_image_file.assert_awaited_once()
        self.assertEqual(Path("a.png"), self.client.image.show_image_file.await_args.kwargs["file_path"])

    async def test_next_shows_a_gif(self):
        self.frame.add_image(PictureFrameGif(Path("a.gif")))

        await self.frame.next()

        self.client.gif.upload_gif_file.assert_awaited_once()
        self.assertEqual(Path("a.gif"), self.client.gif.upload_gif_file.await_args.kwargs["file_path"])

    async def test_next_cycles_through_the_images(self):
        self.frame.add_image(PictureFrameImage(Path("a.png")))
        self.frame.add_image(PictureFrameImage(Path("b.png")))

        for _ in range(3):
            await self.frame.next()

        shown = [call.kwargs["file_path"] for call in self.client.image.show_image_file.await_args_list]
        self.assertEqual([Path("a.png"), Path("b.png"), Path("a.png")], shown)

    async def test_next_does_not_upload_the_same_image_again(self):
        self.frame.add_image(PictureFrameImage(Path("a.png")))

        await self.frame.next()
        await self.frame.next()

        self.client.image.show_image_file.assert_awaited_once()

    async def test_next_without_images_shows_a_black_screen_once(self):
        self.frame._last_set_image = PictureFrameImage(Path("a.png"))

        await self.frame.next()
        await self.frame.next()

        self.client.color.show_color.assert_awaited_once_with(color="black")

    async def test_next_survives_an_upload_error(self):
        self.client.image.show_image_file.side_effect = [RuntimeError("boom"), None]
        self.frame.add_image(PictureFrameImage(Path("broken.png")))
        self.frame.add_image(PictureFrameImage(Path("ok.png")))

        await self.frame.next()
        await self.frame.next()

        self.assertEqual(2, self.client.image.show_image_file.await_count)

    def _shown(self):
        return [call.kwargs["file_path"].name for call in self.client.image.show_image_file.await_args_list]

    def _add_pngs(self, *names):
        for name in names:
            self.frame.add_image(PictureFrameImage(Path(name)))

    async def test_removing_an_image_before_the_current_one_does_not_skip_an_image(self):
        self._add_pngs("a.png", "b.png", "c.png", "d.png")
        await self.frame.next()
        await self.frame.next()  # showing b.png

        self.frame.remove_image(Path("a.png"))
        await self.frame.next()

        self.assertEqual(["a.png", "b.png", "c.png"], self._shown())

    async def test_removing_the_current_image_does_not_skip_an_image(self):
        self._add_pngs("a.png", "b.png", "c.png", "d.png")
        await self.frame.next()
        await self.frame.next()  # showing b.png

        self.frame.remove_image(Path("b.png"))
        await self.frame.next()

        self.assertEqual(["a.png", "b.png", "c.png"], self._shown())

    async def test_removing_an_image_after_the_current_one_changes_nothing(self):
        self._add_pngs("a.png", "b.png", "c.png", "d.png")
        await self.frame.next()

        self.frame.remove_image(Path("d.png"))
        await self.frame.next()
        await self.frame.next()
        await self.frame.next()

        self.assertEqual(["a.png", "b.png", "c.png", "a.png"], self._shown())

    async def test_removing_the_first_image_while_it_is_showing(self):
        self._add_pngs("a.png", "b.png")
        await self.frame.next()

        self.frame.remove_image(Path("a.png"))
        await self.frame.next()

        self.assertEqual(["a.png", "b.png"], self._shown())

    async def test_removing_all_images_and_adding_one_again(self):
        self._add_pngs("a.png")
        await self.frame.next()
        self.frame.remove_image(Path("a.png"))
        await self.frame.next()

        self._add_pngs("b.png")
        await self.frame.next()

        self.assertEqual(["a.png", "b.png"], self._shown())

    async def test_missing_file_does_not_make_the_slideshow_skip_the_next_image(self):
        self.client.image.show_image_file.side_effect = [FileNotFoundError("gone"), None]
        self._add_pngs("gone.png", "b.png", "c.png")

        await self.frame.next()
        await self.frame.next()

        self.assertEqual(["gone.png", "b.png"], self._shown())

    async def test_missing_file_is_removed_from_the_slideshow(self):
        self.client.image.show_image_file.side_effect = FileNotFoundError("gone")
        self.frame.add_image(PictureFrameImage(self.root / "gone.png"))

        await self.frame.next()

        self.assertEqual([], self.frame.images)

    async def test_switching_between_png_and_gif_needs_no_mode_switch_or_reset(self):
        self.frame.add_image(PictureFrameImage(Path("a.png")))
        self.frame.add_image(PictureFrameGif(Path("b.gif")))

        for _ in range(4):
            await self.frame.next()

        self.assertEqual(2, self.client.image.show_image_file.await_count)
        self.assertEqual(2, self.client.gif.upload_gif_file.await_count)
        self.client.image.set_mode.assert_not_called()
        self.client.reset.assert_not_awaited()

    async def test_start_pause_resume_and_stop(self):
        self.frame.add_image(PictureFrameImage(Path("a.png")))

        task = await self.frame.start_slideshow(interval=1)
        self.assertTrue(self.frame.is_slideshow_running())

        await self.frame.pause_slideshow()
        self.assertFalse(self.frame.is_slideshow_running())

        await self.frame.resume_slideshow()
        self.assertTrue(self.frame.is_slideshow_running())

        await self.frame.stop_slideshow()
        await asyncio.sleep(0)
        self.assertTrue(task.cancelled() or task.done())
        self.assertFalse(self.frame.is_slideshow_running())
        self.client.clock.show.assert_awaited_once()
        self.client.disconnect.assert_awaited_once()

    async def test_slideshow_shows_images(self):
        self.frame.add_image(PictureFrameImage(Path("a.png")))

        await self.frame.start_slideshow(interval=1)
        await _eventually(lambda: self.client.image.show_image_file.await_count >= 1)
        await self.frame.stop_slideshow()

        self.client.image.show_image_file.assert_awaited()

    async def test_disconnect_pauses_and_connect_resumes(self):
        listener = self.client.add_connection_listener.call_args.args[0]
        await self.frame.start_slideshow(interval=1)
        self.addCleanup(self.frame._slideshow_task.cancel)

        await listener.on_disconnected()
        self.assertFalse(self.frame.is_slideshow_running())
        self.assertIsNone(self.frame._last_set_image)

        await listener.on_connected()
        self.assertTrue(self.frame.is_slideshow_running())
