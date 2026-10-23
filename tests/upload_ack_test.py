import asyncio
from unittest.mock import patch

from idotmatrix.connection_manager import CommandRejectedError, UploadError
from idotmatrix.util.command_ack import is_acknowledged_command
from idotmatrix.util.upload_ack import UploadStatus, parse_upload_notification
from tests import TestBase
from tests.fake_device import FakeDeviceTestBase

GIF_NEXT = bytes.fromhex("0500010001")
GIF_FINISHED = bytes.fromhex("0500010003")
IMAGE_NEXT = bytes.fromhex("0500000002")
IMAGE_FINISHED = bytes.fromhex("0500000001")


class TestParseUploadNotification(TestBase):

    def test_gif(self):
        self.assertEqual(UploadStatus.NEXT, parse_upload_notification(GIF_NEXT))
        self.assertEqual(UploadStatus.FINISHED, parse_upload_notification(GIF_FINISHED))
        self.assertEqual(UploadStatus.ERROR, parse_upload_notification(bytes.fromhex("0500010002")))
        self.assertEqual(UploadStatus.ERROR, parse_upload_notification(bytes.fromhex("0500010000")))

    def test_diy_image(self):
        self.assertEqual(UploadStatus.NEXT, parse_upload_notification(IMAGE_NEXT))
        self.assertEqual(UploadStatus.FINISHED, parse_upload_notification(IMAGE_FINISHED))
        self.assertEqual(UploadStatus.FINISHED, parse_upload_notification(bytes.fromhex("0500000000")))

    def test_unrelated_notifications_are_ignored(self):
        for data in (b"", b"\x05\x00\x01", bytes.fromhex("0500040101"), bytes.fromhex("0900010001"[:8])):
            with self.subTest(data=data.hex()):
                self.assertIsNone(parse_upload_notification(data))

    def test_longer_notifications_are_parsed_by_their_first_bytes(self):
        self.assertEqual(UploadStatus.NEXT, parse_upload_notification(GIF_NEXT + b"\x00\x00"))


class TestUploadFlowControl(FakeDeviceTestBase):

    async def test_subscribes_to_notifications_on_connect(self):
        await self.under_test.connect()

        self.transport.start_notify.assert_awaited_once()

    async def test_subscribes_again_after_reconnecting(self):
        await self.under_test.connect()
        await self.under_test.disconnect()
        self.transport.is_connected = False

        await self.under_test.connect()

        self.assertEqual(2, self.transport.start_notify.await_count)

    async def test_waits_for_the_ack_of_each_packet_before_sending_the_next(self):
        self.replies = [GIF_NEXT, GIF_NEXT, GIF_FINISHED]
        order = []
        original_wait = self.under_test._wait_for_upload_status

        async def spy(deadline):
            order.append("wait")
            return await original_wait(deadline)

        self.under_test._wait_for_upload_status = spy
        self.transport.write.side_effect = self._recording_write(order)

        await self.under_test.send_packets([[b"a"], [b"b"], [b"c"]], response=True, wait_for_ack=True)

        self.assertEqual(["write:a", "wait", "write:b", "wait", "write:c", "wait"], order)

    def _recording_write(self, order):
        original = self.transport._write

        async def write(data, response):
            order.append(f"write:{bytes(data).decode()}")
            await original(data=data, response=response)

        return write

    async def test_without_wait_for_ack_nothing_is_awaited(self):
        await self.under_test.send_packets([[b"a"], [b"b"]], response=True)

        self.assertEqual(2, self.transport.write.await_count)

    async def test_never_reads_the_notification_characteristic(self):
        self.replies = [GIF_NEXT, GIF_FINISHED]

        await self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True)

        self.transport.read.assert_not_awaited()

    async def test_stops_when_the_device_reports_that_it_is_finished(self):
        # the device answers "finished" right away if it already has the same file stored
        self.replies = [GIF_FINISHED]

        await self.under_test.send_packets([[b"a"], [b"b"], [b"c"]], response=True, wait_for_ack=True)

        self.assertEqual([("write", b"a")], self.events)

    async def test_image_acks(self):
        self.replies = [IMAGE_NEXT, IMAGE_FINISHED]

        await self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True)

        self.assertEqual(2, len(self.events))

    async def test_raises_if_the_device_rejects_the_upload(self):
        self.replies = [GIF_NEXT, bytes.fromhex("0500010002")]

        with self.assertRaisesRegex(UploadError, "0500010002"):
            await self.under_test.send_packets([[b"a"], [b"b"], [b"c"]], response=True, wait_for_ack=True)

        self.assertEqual(2, len(self.events))

    async def test_raises_if_the_device_does_not_answer(self):
        with patch("idotmatrix.connection_manager.UPLOAD_ACK_TIMEOUT_SECONDS", 0.05):
            with self.assertRaises(UploadError):
                await self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True)

        self.assertEqual(1, len(self.events))

    async def test_unrelated_notifications_are_skipped_while_waiting(self):
        self.replies = [GIF_FINISHED]
        write = self.transport._write

        async def write_with_noise(data, response):
            self.transport.notify(bytes.fromhex("0500040101"))
            await write(data=data, response=response)

        self.transport.write.side_effect = write_with_noise

        await self.under_test.send_packets([[b"a"]], response=True, wait_for_ack=True)

    async def test_stale_notifications_are_discarded_before_an_upload(self):
        await self.under_test.connect()
        # a leftover from an earlier upload, which would be taken for the ack of the first packet
        self.transport.notify(GIF_FINISHED)
        self.replies = [GIF_NEXT, GIF_NEXT]

        await self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True)

        self.assertEqual(2, len(self.events))

    async def test_does_not_wait_if_notifications_are_not_available(self):
        self.transport.start_notify.side_effect = RuntimeError("no notify")

        with patch("idotmatrix.connection_manager.UPLOAD_ACK_TIMEOUT_SECONDS", 0.05):
            await asyncio.wait_for(
                self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True), timeout=2)

        self.assertEqual(2, len(self.events))

    async def test_paces_the_ble_packets_of_a_chunk(self):
        # GIVEN
        self.replies = [GIF_FINISHED]
        self.transport.reply_to_any_write = True
        sleeps = []

        async def record_sleep(seconds):
            sleeps.append(seconds)

        # WHEN
        with patch("idotmatrix.connection_manager.asyncio.sleep", record_sleep):
            await self.under_test.send_packets([[b"a", b"b", b"c"]], response=False, wait_for_ack=True)

        # THEN
        self.assertEqual([0.02, 0.02], [s for s in sleeps if s])

    async def test_uploads_write_every_packet_with_response(self):
        # GIVEN
        self.replies = [GIF_FINISHED]

        # WHEN
        await self.under_test.send_packets([[b"a", b"b", b"c"]], response=True, wait_for_ack=True)

        # THEN each write is answered by the device, so there is no burst the Bluetooth stack could drop
        responses = [call.kwargs["response"] for call in self.transport.write.await_args_list]
        self.assertEqual([True, True, True], responses)

    async def test_without_ack_only_the_last_packet_is_written_with_response(self):
        # WHEN
        await self.under_test.send_packets([[b"a", b"b", b"c"]], response=True)

        # THEN
        responses = [call.kwargs["response"] for call in self.transport.write.await_args_list]
        self.assertEqual([False, False, True], responses)

    async def test_does_not_pace_writes_without_ack(self):
        # GIVEN
        sleeps = []

        async def record_sleep(seconds):
            sleeps.append(seconds)

        # WHEN
        with patch("idotmatrix.connection_manager.asyncio.sleep", record_sleep):
            await self.under_test.send_packets([[b"a", b"b", b"c"]], response=True)

        # THEN
        self.assertEqual([], [s for s in sleeps if s])

    async def test_ack_timeout_counts_from_the_start_of_the_chunk(self):
        # GIVEN
        loop_time = asyncio.get_running_loop().time
        deadlines = []
        original_wait = self.under_test._wait_for_upload_status

        async def spy(deadline):
            deadlines.append(deadline)
            return await original_wait(deadline)

        self.under_test._wait_for_upload_status = spy
        self.replies = [GIF_FINISHED]

        # WHEN
        started = loop_time()
        await self.under_test.send_packets([[b"a", b"b"]], response=True, wait_for_ack=True)

        # THEN the deadline was taken before the 20 ms pause between the two writes
        self.assertLess(deadlines[0], started + 5 + 0.02)


class TestCommandAcks(FakeDeviceTestBase):
    """Normal commands are answered with 05 00 <command> <subcommand> <status>, 01 = accepted, 00 = rejected."""

    BRIGHTNESS = bytearray([5, 0, 4, 128, 50])

    def _answer_with(self, *notifications):
        self.replies = list(notifications)

    async def test_waits_for_the_ack_of_the_command(self):
        self._answer_with(bytes.fromhex("0500048001"))
        order = []
        original_wait = self.under_test._wait_for_command_ack

        async def spy(command):
            order.append("wait")
            return await original_wait(command)

        self.under_test._wait_for_command_ack = spy

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

        self.assertEqual(["wait"], order)

    async def test_raises_if_the_device_rejects_the_command(self):
        self._answer_with(bytes.fromhex("0500048000"))

        with self.assertRaisesRegex(CommandRejectedError, "0500048000"):
            await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

    async def test_acks_of_other_commands_are_skipped(self):
        write = self.transport._write

        async def write_with_noise(data, response):
            self.transport.notify(bytes.fromhex("0500060100"))  # a rejection of ANOTHER command
            self.transport.notify(bytes.fromhex("0900018005090104"))  # something else entirely
            self.transport.notify(bytes.fromhex("0500048001"))
            await write(data=data, response=response)

        self.transport.write.side_effect = write_with_noise

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

    async def test_stale_acks_are_discarded(self):
        await self.under_test.connect()
        self.transport.notify(bytes.fromhex("0500048000"))  # rejection of an earlier command
        self._answer_with(bytes.fromhex("0500048001"))

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

    async def test_a_missing_ack_is_only_logged(self):
        with patch("idotmatrix.connection_manager.COMMAND_ACK_TIMEOUT_SECONDS", 0.05):
            with self.assertLogs("idotmatrix.connection_manager", level="WARNING"):
                await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

        self.assertEqual(1, len(self.events))

    async def test_does_not_wait_if_notifications_are_not_available(self):
        self.transport.start_notify.side_effect = RuntimeError("no notify")

        await asyncio.wait_for(
            self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True), timeout=2)

        self.assertEqual(1, len(self.events))

    async def test_large_commands_are_written_completely_before_waiting_for_the_ack(self):
        self.under_test._max_ble_packet_size_override = 3
        self.transport.reply_to_any_write = True
        self._answer_with(bytes.fromhex("0500048001"))

        await self.under_test.send_bytes(self.BRIGHTNESS, response=False, wait_for_ack=True)

        # both chunks were written, the single ack was found afterwards
        self.assertEqual(2, len(self.events))

    async def test_acknowledged_commands_are_waited_for_by_default(self):
        self._answer_with(bytes.fromhex("0500048000"))

        with self.assertRaises(CommandRejectedError):
            await self.under_test.send_bytes(self.BRIGHTNESS, response=True)

    async def test_returns_whether_the_command_was_acknowledged(self):
        self._answer_with(bytes.fromhex("0500048001"))

        self.assertTrue(await self.under_test.send_bytes(self.BRIGHTNESS, response=True))
        self.assertFalse(await self.under_test.send_bytes(bytearray([5, 0, 99, 128, 1]), response=True))

    async def test_commands_that_are_not_acknowledged_are_not_waited_for(self):
        # set_speed is never answered, waiting would cost the whole timeout and a warning every time
        with self.assertNoLogs("idotmatrix.connection_manager", level="WARNING"):
            await asyncio.wait_for(
                self.under_test.send_bytes(bytearray([5, 0, 3, 128, 50]), response=True), timeout=0.5)

    async def test_waiting_can_be_turned_off(self):
        self._answer_with(bytes.fromhex("0500048000"))

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=False)

    async def test_waiting_can_be_forced(self):
        with patch("idotmatrix.connection_manager.COMMAND_ACK_TIMEOUT_SECONDS", 0.05):
            with self.assertLogs("idotmatrix.connection_manager", level="WARNING"):
                await self.under_test.send_bytes(bytearray([5, 0, 99, 128, 1]), response=True, wait_for_ack=True)


class TestIsAcknowledgedCommand(TestBase):

    def test_known_commands(self):
        for command in ([5, 0, 4, 128, 50], [8, 0, 6, 1, 0, 255, 255, 255], [5, 0, 7, 1, 1], [6, 0, 11, 128, 1, 50]):
            with self.subTest(command=command):
                self.assertTrue(is_acknowledged_command(bytearray(command)))

    def test_unknown_commands(self):
        for command in ([4, 0, 3, 0], [5, 0, 3, 128, 50], [5, 0, 12, 128, 0], [11, 0, 1, 128, 1, 2, 3, 4, 5, 6, 7], []):
            with self.subTest(command=command):
                self.assertFalse(is_acknowledged_command(bytearray(command)))

    def test_text_and_upload_packets_are_not_commands(self):
        text_packet = bytearray([30, 1, 3, 0, 0, 0, 0, 0])
        self.assertFalse(is_acknowledged_command(text_packet))
