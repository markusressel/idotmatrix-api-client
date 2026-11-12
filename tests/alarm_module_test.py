import io
import zlib
from datetime import datetime
from unittest.mock import AsyncMock, patch

from PIL import Image

from idotmatrix.modules.alarm import AlarmModule, Weekday
from idotmatrix.modules.common import CommonModule
from idotmatrix.modules.gif import GifModule
from idotmatrix.screensize import ScreenSize
from tests import TestBase

# 4183 bytes, like the GIF of the capture of the official app in issue #51
GIF_DATA = b"GIF89a" + bytes(range(256)) * 16 + bytes(4183 - 6 - 4096)


class TestAlarmModule(TestBase):

    def setUp(self):
        super().setUp()
        self.connection_manager = AsyncMock()
        self.gif = GifModule(connection_manager=self.connection_manager, screen_size=ScreenSize.SIZE_16x16)
        self.common = CommonModule(connection_manager=self.connection_manager)
        self.under_test = AlarmModule(connection_manager=self.connection_manager, gif=self.gif, common=self.common)

    def _parts(self) -> list[bytes]:
        """The parts of the alarm that was sent, with the BLE packets of each part joined."""
        packets = self.connection_manager.send_packets.await_args.kwargs["packets"]
        return [b"".join(ble_packets) for ble_packets in packets]

    def test_create_alarm_packets_like_the_official_app(self):
        # GIVEN the settings of the capture in issue #51: slot 0, once, 21:18, 10 s, GIF, buzzer on
        crc = zlib.crc32(GIF_DATA).to_bytes(4, "little")

        # WHEN
        packets = AlarmModule._create_alarm_packets(
            gif_data=GIF_DATA, slot=0, flags=0x01, hour=21, minute=18, ring_duration=10, buzzer=True)

        # THEN the header of the capture, repeated in front of each part of 4096 bytes. The CRC is the one of our data:
        # the GIF of the capture is not known, so the CRC variant (zlib CRC-32, like for GIF uploads) is not confirmed
        parts = [b"".join(ble_packets) for ble_packets in packets]
        self.assertEqual(2, len(parts))
        self.assertEqual(bytes.fromhex("18100080000115120a0001010057100000") + crc + bytes.fromhex("000014"),
                         parts[0][:24])
        self.assertEqual(bytes.fromhex("6f000080000115120a0001010257100000") + crc + bytes.fromhex("000014"),
                         parts[1][:24])
        self.assertEqual(GIF_DATA, parts[0][24:] + parts[1][24:])

    def test_create_alarm_packets_splits_into_ble_packets(self):
        # WHEN
        packets = AlarmModule._create_alarm_packets(
            gif_data=GIF_DATA, slot=0, flags=0x01, hour=21, minute=18, ring_duration=10, buzzer=True)

        # THEN
        self.assertTrue(all(len(ble_packet) <= 509 for packet in packets for ble_packet in packet))

    def test_create_alarm_packets_rejects_empty_data(self):
        with self.assertRaises(ValueError):
            AlarmModule._create_alarm_packets(
                gif_data=b"", slot=0, flags=1, hour=0, minute=0, ring_duration=10, buzzer=True)

    async def test_set_alarm(self):
        # GIVEN
        with patch.object(self.gif, "_load_gif_and_adapt_to_canvas", return_value=GIF_DATA) as convert:
            # WHEN
            await self.under_test.set_alarm(
                slot=3, hour=7, minute=30, file_path="alarm.gif", weekdays=[Weekday.MONDAY, Weekday.FRIDAY],
                ring_duration=300, buzzer=False, sync_time=False)

        # THEN the picture is converted to the size of the screen
        self.assertEqual("alarm.gif", convert.call_args.kwargs["file_path"])
        self.assertEqual(16, convert.call_args.kwargs["canvas_size"])
        # AND the parts are sent like an upload, waiting for the acknowledgement of each
        kwargs = self.connection_manager.send_packets.await_args.kwargs
        self.assertTrue(kwargs["response"])
        self.assertTrue(kwargs["wait_for_ack"])
        # AND the header has the settings: enabled, Monday (bit 1) and Friday (bit 5), 300 s, no buzzer, id 23
        self.assertEqual(bytes.fromhex("18100080032307 1e 2c01 01 00 00".replace(" ", "")), self._parts()[0][:13])
        self.assertEqual(23, self._parts()[0][23])
        self.connection_manager.send_bytes.assert_not_awaited()

    async def test_set_alarm_sets_the_time_first(self):
        # GIVEN
        calls = []
        self.connection_manager.send_bytes.side_effect = lambda **kwargs: calls.append("time")
        self.connection_manager.send_packets.side_effect = lambda **kwargs: calls.append("alarm")

        with patch.object(self.gif, "_load_gif_and_adapt_to_canvas", return_value=GIF_DATA), \
                patch("idotmatrix.modules.alarm.datetime") as clock:
            clock.now.return_value = datetime(2025, 1, 6, 13, 14, 15)
            # WHEN
            await self.under_test.set_alarm(slot=0, hour=13, minute=20, file_path="alarm.gif")

        # THEN
        self.assertEqual(["time", "alarm"], calls)
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray([11, 0, 1, 128, 25, 1, 6, 1, 13, 14, 15]), response=True)
        # AND the defaults: once, 10 s, buzzer on
        self.assertEqual(bytes.fromhex("1810008000010d140a000101"), self._parts()[0][:12])

    async def test_set_alarm_with_a_real_picture(self):
        # GIVEN
        path = self._test_folder / "data" / "demo.gif"

        # WHEN
        await self.under_test.set_alarm(slot=0, hour=6, minute=0, file_path=path, sync_time=False)

        # THEN the picture is a GIF of the size of the screen
        gif = b"".join(part[24:] for part in self._parts())
        self.assertEqual((16, 16), Image.open(io.BytesIO(gif)).size)
        self.assertEqual(len(gif), int.from_bytes(self._parts()[0][13:17], "little"))

    async def test_set_alarm_validates_before_converting(self):
        invalid = [
            dict(slot=10), dict(slot=-1), dict(slot=True), dict(hour=24), dict(minute=60), dict(ring_duration=0),
            dict(ring_duration=0x10000), dict(weekdays=[7]), dict(weekdays=["monday"]),
        ]
        for arguments in invalid:
            with self.subTest(arguments=arguments), \
                    patch.object(self.gif, "_load_gif_and_adapt_to_canvas") as convert:
                with self.assertRaises(ValueError):
                    await self.under_test.set_alarm(
                        **{"slot": 0, "hour": 6, "minute": 0, "file_path": "alarm.gif", **arguments})
                convert.assert_not_called()
        self.connection_manager.send_packets.assert_not_awaited()

    async def test_disable_alarm(self):
        # WHEN
        await self.under_test.disable_alarm(slot=0, hour=21, minute=18, ring_duration=10)

        # THEN the first 12 bytes of the header, with the enabled bit cleared (TimerAgreement of the app)
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(bytes.fromhex("0c000080000015120a000101")), response=False)

    async def test_disable_alarm_keeps_the_weekdays(self):
        # WHEN
        await self.under_test.disable_alarm(
            slot=2, hour=6, minute=5, weekdays=[Weekday.SUNDAY], ring_duration=900, buzzer=False)

        # THEN Sunday is bit 7
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(bytes.fromhex("0c00008002800605840301 00".replace(" ", ""))), response=False)

    async def test_disable_alarm_validates(self):
        with self.assertRaises(ValueError):
            await self.under_test.disable_alarm(slot=10, hour=0, minute=0)
        self.connection_manager.send_bytes.assert_not_awaited()
