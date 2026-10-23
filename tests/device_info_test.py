from idotmatrix.screensize import ScreenSize
from idotmatrix.util.device_info import parse_device_info
from tests import TestBase
from tests.fake_device import FakeDeviceTestBase

SET_TIME_REPLY = bytes.fromhex("090001800509010400")


class TestParseDeviceInfo(TestBase):

    def test_reply_of_a_64x64(self):
        info = parse_device_info(SET_TIME_REPLY)

        self.assertEqual("5.09", info.firmware_version)
        self.assertEqual(4, info.screen_type)
        self.assertEqual(ScreenSize.SIZE_64x64, info.screen_size)
        self.assertFalse(info.password_protected)
        self.assertEqual(1, info.switch_status)

    def test_password_flag(self):
        self.assertTrue(parse_device_info(bytes.fromhex("090001800509010401")).password_protected)

    def test_minor_version_has_two_digits(self):
        self.assertEqual("1.00", parse_device_info(bytes.fromhex("090001800100010400")).firmware_version)

    def test_screen_types(self):
        for screen_type, size in ((1, ScreenSize.SIZE_16x16), (3, ScreenSize.SIZE_32x32), (4, ScreenSize.SIZE_64x64),
                                  (2, None), (11, None)):
            with self.subTest(screen_type=screen_type):
                info = parse_device_info(bytes([9, 0, 1, 128, 5, 9, 1, screen_type, 0]))
                self.assertEqual(size, info.screen_size)

    def test_other_notifications_are_ignored(self):
        for data in (b"", bytes.fromhex("0500048001"), bytes.fromhex("0900018005090104")):
            with self.subTest(data=data.hex()):
                self.assertIsNone(parse_device_info(data))


class TestRequest(FakeDeviceTestBase):
    COMMAND = bytes([11, 0, 1, 128, 25, 1, 6, 1, 13, 14, 15])

    async def test_returns_the_answer(self):
        self.replies = [SET_TIME_REPLY]

        self.assertEqual(SET_TIME_REPLY, await self.under_test.request(self.COMMAND))

    async def test_skips_other_notifications(self):
        self.replies = [bytes.fromhex("0500048001")]
        write = self.transport.write.side_effect

        async def write_with_reply(data, response):
            await write(data, response)
            self.transport.notify(SET_TIME_REPLY)

        self.transport.write.side_effect = write_with_reply

        self.assertEqual(SET_TIME_REPLY, await self.under_test.request(self.COMMAND))

    async def test_returns_none_without_an_answer(self):
        self.assertIsNone(await self.under_test.request(self.COMMAND, timeout=0.05))

    async def test_returns_none_if_notifications_are_not_available(self):
        self.transport.start_notify.side_effect = RuntimeError("no notify")

        self.assertIsNone(await self.under_test.request(self.COMMAND))
        self.assertEqual(1, len(self.events))
