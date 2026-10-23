from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

from PIL import Image

from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.modules.materials import MaterialsModule
from idotmatrix.screensize import ScreenSize
from tests import TestBase


class TestMaterialsModule(TestBase):

    def setUp(self):
        super().setUp()
        self.connection_manager = AsyncMock()
        self.gif = GifModule(connection_manager=self.connection_manager, screen_size=ScreenSize.SIZE_64x64)
        self.image = ImageModule(connection_manager=self.connection_manager, screen_size=ScreenSize.SIZE_64x64)
        self.under_test = MaterialsModule(connection_manager=self.connection_manager, gif=self.gif, image=self.image)

    def _headers(self):
        """The 16 byte headers of the uploads (first BLE packet of each chunk), one list per upload."""
        uploads = []
        for call in self.connection_manager.send_packets.await_args_list:
            uploads.append([bytes(chunk[0][:16]) for chunk in call.kwargs["packets"]])
        return uploads

    async def test_clear_all_slots(self):
        # WHEN
        await self.under_test.clear()

        # THEN the command of the official app: length, command, number of slots, slots
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(bytes.fromhex("11000201" "0c" "000102030405060708090a0b")), response=True)

    async def test_clear_some_slots(self):
        # WHEN
        await self.under_test.clear([3, 1])

        # THEN
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(bytes.fromhex("07000201" "02" "0103")), response=True)

    async def test_clear_rejects_invalid_slots(self):
        for slots in ([12], [-1], [1, 1], [], ["1"], [True]):
            with self.subTest(slots=slots):
                with self.assertRaises(ValueError):
                    await self.under_test.clear(slots)
        self.connection_manager.send_bytes.assert_not_awaited()

    async def test_store_puts_files_into_the_slots_in_order(self):
        # GIVEN
        gif = self._test_data_folder / "demo.gif"
        image = self._test_data_folder / "demo_64.png"

        # WHEN
        used = await self.under_test.store([gif, image], slots=[7, 4], display_time=30)

        # THEN each file goes into one slot, in the order of the slot numbers, and nothing is deleted
        self.assertEqual([4, 7], used)
        self.connection_manager.send_bytes.assert_not_awaited()
        gif_header, image_header = [headers[0] for headers in self._headers()]
        self.assertEqual((1, 4, 30), (gif_header[2], gif_header[15], int.from_bytes(gif_header[13:15], "little")))
        self.assertEqual((2, 7, 30), (image_header[2], image_header[15], int.from_bytes(image_header[13:15], "little")))

    async def test_store_defaults_to_all_slots_and_deletes_the_others(self):
        # WHEN
        used = await self.under_test.store([self._test_data_folder / "demo_64.png"] * 2)

        # THEN only as many slots as files are filled, from the first one, the rest of the allowed slots is emptied
        self.assertEqual([0, 1], used)
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(bytes.fromhex("0f000201" "0a" "02030405060708090a0b")), response=True)

    async def test_store_only_deletes_unused_slots_that_are_allowed(self):
        # WHEN
        await self.under_test.store([self._test_data_folder / "demo_64.png"], slots=[5, 6, 8])

        # THEN slot 5 gets the file, 6 and 8 are emptied, all others are left alone
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(bytes.fromhex("07000201" "02" "0608")), response=True)

    async def test_store_without_clearing_unused_slots(self):
        # WHEN
        await self.under_test.store([self._test_data_folder / "demo_64.png"], clear_unused=False)

        # THEN
        self.connection_manager.send_bytes.assert_not_awaited()

    async def test_store_rejects_more_files_than_slots(self):
        with self.assertRaisesRegex(ValueError, "3 files do not fit into 2 slots"):
            await self.under_test.store([self._test_data_folder / "demo_64.png"] * 3, slots=[0, 1])

        self.connection_manager.send_bytes.assert_not_awaited()
        self.connection_manager.send_packets.assert_not_awaited()

    async def test_store_rejects_an_invalid_display_time(self):
        for display_time in (0, 70000, "5"):
            with self.subTest(display_time=display_time):
                with self.assertRaises(ValueError):
                    await self.under_test.store([self._test_data_folder / "demo_64.png"], display_time=display_time)

    async def test_store_nothing(self):
        self.assertEqual([], await self.under_test.store([]))
        self.connection_manager.send_bytes.assert_not_awaited()


class TestMaterialsPlanning(TestBase):
    """What is already in a slot stays there, only what is new is transferred."""

    def setUp(self):
        super().setUp()
        self.connection_manager = AsyncMock()
        self.gif = GifModule(connection_manager=self.connection_manager, screen_size=ScreenSize.SIZE_64x64)
        self.image = ImageModule(connection_manager=self.connection_manager, screen_size=ScreenSize.SIZE_64x64)
        self.under_test = MaterialsModule(connection_manager=self.connection_manager, gif=self.gif, image=self.image)
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def _picture(self, name: str, color: int) -> Path:
        path = Path(self.folder.name) / name
        Image.new("RGB", (64, 64), (color, 0, 0)).save(path)
        return path

    def _uploads(self) -> list[int]:
        """The slots that data was transferred to, in order."""
        return [call.kwargs["packets"][0][0][15] for call in self.connection_manager.send_packets.await_args_list]

    async def test_the_same_files_are_not_transferred_again(self):
        # GIVEN
        files = [self._picture(f"{n}.png", n) for n in range(3)]
        slots = await self.under_test.store(files)
        self.connection_manager.send_packets.reset_mock()

        # WHEN
        again = await self.under_test.store(files)

        # THEN
        self.assertEqual(slots, again)
        self.connection_manager.send_packets.assert_not_awaited()

    async def test_files_in_another_order_keep_their_slots(self):
        # GIVEN
        files = [self._picture(f"{n}.png", n) for n in range(3)]
        slots = await self.under_test.store(files)
        self.connection_manager.send_packets.reset_mock()

        # WHEN
        reordered = await self.under_test.store(files[::-1])

        # THEN nothing is transferred and every file stays in its slot (the device cycles in the order of the slots)
        self.assertEqual(slots[::-1], reordered)
        self.connection_manager.send_packets.assert_not_awaited()

    async def test_only_the_new_file_is_transferred_into_the_slot_that_is_no_longer_needed(self):
        # GIVEN
        files = [self._picture(f"{n}.png", n) for n in range(3)]
        await self.under_test.store(files, slots=[0, 1, 2])
        self.connection_manager.send_packets.reset_mock()

        # WHEN the first file is replaced by a new one
        new = self._picture("new.png", 99)
        slots = await self.under_test.store([new, files[1], files[2]], slots=[0, 1, 2])

        # THEN
        self.assertEqual([0, 1, 2], slots)
        self.assertEqual([0], self._uploads())

    async def test_a_file_that_is_added_in_front_does_not_move_the_others(self):
        # GIVEN
        files = [self._picture(f"{n}.png", n) for n in range(3)]
        await self.under_test.store(files, slots=[0, 1, 2, 3])
        self.connection_manager.send_packets.reset_mock()

        # WHEN
        slots = await self.under_test.store([self._picture("new.png", 99)] + files, slots=[0, 1, 2, 3])

        # THEN
        self.assertEqual([3, 0, 1, 2], slots)
        self.assertEqual([3], self._uploads())

    async def test_changed_content_options_or_display_time_are_transferred_again(self):
        # GIVEN
        file = self._picture("a.png", 1)
        await self.under_test.store([file], slots=[0], display_time=10)
        for kwargs in ({"display_time": 20}, {"palletize": True}, {"background_color": (1, 2, 3)}):
            with self.subTest(kwargs=kwargs):
                self.connection_manager.send_packets.reset_mock()

                # WHEN
                await self.under_test.store([file], slots=[0], **{"display_time": 10, **kwargs})
                await self.under_test.store([file], slots=[0], display_time=10)

                # THEN
                self.assertEqual([0, 0], self._uploads())

        self.connection_manager.send_packets.reset_mock()
        file.write_bytes(self._picture("b.png", 2).read_bytes())
        await self.under_test.store([file], slots=[0], display_time=10)
        self.assertEqual([0], self._uploads())

    async def test_verify_sends_everything_again(self):
        # GIVEN
        files = [self._picture(f"{n}.png", n) for n in range(2)]
        await self.under_test.store(files)
        self.connection_manager.send_packets.reset_mock()

        # WHEN
        await self.under_test.store(files, verify=True)

        # THEN
        self.assertEqual(2, len(self._uploads()))

    async def test_keep_order_puts_the_files_into_the_slots_in_order(self):
        # GIVEN
        files = [self._picture(f"{n}.png", n) for n in range(2)]
        await self.under_test.store(files)

        # WHEN
        slots = await self.under_test.store(files[::-1], keep_order=True)

        # THEN
        self.assertEqual([0, 1], slots)

    async def test_slots_that_are_known_to_be_empty_are_not_deleted_again(self):
        # GIVEN
        file = self._picture("a.png", 1)
        await self.under_test.store([file], slots=[0, 1, 2])
        self.assertEqual(1, self.connection_manager.send_bytes.await_count)  # the unused slots 1 and 2
        self.connection_manager.send_bytes.reset_mock()

        # WHEN
        await self.under_test.store([file], slots=[0, 1, 2])

        # THEN
        self.connection_manager.send_bytes.assert_not_awaited()

    async def test_a_slot_whose_upload_failed_is_not_trusted(self):
        # GIVEN
        file = self._picture("a.png", 1)
        self.connection_manager.send_packets.side_effect = [RuntimeError("lost"), None]
        with self.assertRaises(RuntimeError):
            await self.under_test.store([file], slots=[0])

        # WHEN
        await self.under_test.store([file], slots=[0])

        # THEN it was sent again
        self.assertEqual(2, self.connection_manager.send_packets.await_count)

    async def test_clear_forgets_the_slots(self):
        # GIVEN
        file = self._picture("a.png", 1)
        await self.under_test.store([file], slots=[0])
        await self.under_test.clear([0])
        self.connection_manager.send_packets.reset_mock()

        # WHEN
        await self.under_test.store([file], slots=[0])

        # THEN
        self.assertEqual([0], self._uploads())


class TestUploadWithSlot(TestBase):

    async def test_gif_goes_into_the_slot_with_the_display_time(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)

        # WHEN
        await under_test.upload_gif_file(self._test_data_folder / "demo.gif", slot=3, display_time=300)

        # THEN
        header = bytes(connection_manager.send_packets.await_args.kwargs["packets"][0][0][:16])
        self.assertEqual(3, header[15])
        self.assertEqual(300, int.from_bytes(header[13:15], "little"))

    async def test_image_goes_into_the_slot_with_the_display_time(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)

        # WHEN
        await under_test.show_image_file(self._test_data_folder / "demo_64.png", slot=11, display_time=10)

        # THEN
        header = bytes(connection_manager.send_packets.await_args.kwargs["packets"][0][0][:16])
        self.assertEqual(11, header[15])
        self.assertEqual(10, int.from_bytes(header[13:15], "little"))

    async def test_without_a_slot_it_is_shown_right_away(self):
        # GIVEN
        connection_manager = AsyncMock()
        gif = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        image = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)

        # WHEN
        await gif.upload_gif_file(self._test_data_folder / "demo.gif")
        await image.show_image_file(self._test_data_folder / "demo_64.png")

        # THEN the index is 13 (show now), the time is still the 5 s of the app
        for call in connection_manager.send_packets.await_args_list:
            header = bytes(call.kwargs["packets"][0][0][:16])
            self.assertEqual(13, header[15])
            self.assertEqual(5, int.from_bytes(header[13:15], "little"))

    async def test_invalid_slot_or_time(self):
        connection_manager = AsyncMock()
        gif = GifModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)
        image = ImageModule(connection_manager=connection_manager, screen_size=ScreenSize.SIZE_64x64)

        for upload in (gif.upload_gif_file, image.show_image_file):
            for kwargs in ({"slot": 12}, {"slot": -1}, {"slot": 1, "display_time": 0}):
                with self.subTest(upload=upload.__name__, kwargs=kwargs):
                    with self.assertRaises(ValueError):
                        await upload(self._test_data_folder / "demo.gif", **kwargs)
        connection_manager.send_packets.assert_not_awaited()
