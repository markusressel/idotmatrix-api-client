import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from idotmatrix.connection_manager import CommandRejectedError, ConnectionManager, UploadError
from idotmatrix.const import UUID_READ_DATA
from idotmatrix.util.upload_ack import UploadStatus, parse_upload_notification
from tests import TestBase

ADDRESS = "00:11:22:33:44:55"

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


class FakeDeviceTestBase(TestBase):

    def setUp(self):
        patcher = patch("idotmatrix.connection_manager.BleakClient")
        bleak_client_cls = patcher.start()
        self.addCleanup(patcher.stop)

        self.client = MagicMock()
        self.client.is_connected = False
        self.client.mtu_size = None
        self.client._backend = MagicMock(spec=[])
        self.client.services = MagicMock()
        self.client.services.__iter__.return_value = iter([])
        self.client.services.get_characteristic.return_value.max_write_without_response_size = 514
        self.client.disconnect = AsyncMock()
        self.client.read_gatt_char = AsyncMock()
        self.events = []
        self.listener = None
        self.replies = []
        self.reply_to_any_write = False

        async def connect():
            self.client.is_connected = True

        async def start_notify(uuid, callback):
            self.assertEqual(UUID_READ_DATA, uuid)
            self.listener = callback

        async def write(char_specifier, data, response):
            self.events.append(("write", bytes(data)))
            # the device answers once a full protocol packet has been received
            if (response or self.reply_to_any_write) and self.replies:
                self.listener(None, bytearray(self.replies.pop(0)))

        self.client.connect = AsyncMock(side_effect=connect)
        self.client.start_notify = AsyncMock(side_effect=start_notify)
        self.client.write_gatt_char = AsyncMock(side_effect=write)
        bleak_client_cls.return_value = self.client

        self.under_test = ConnectionManager(address=ADDRESS)



class TestUploadFlowControl(FakeDeviceTestBase):

    async def test_subscribes_to_notifications_on_connect(self):
        await self.under_test.connect()

        self.client.start_notify.assert_awaited_once()

    async def test_subscribes_again_after_reconnecting(self):
        await self.under_test.connect()
        await self.under_test.disconnect()
        self.client.is_connected = False

        await self.under_test.connect()

        self.assertEqual(2, self.client.start_notify.await_count)

    async def test_waits_for_the_ack_of_each_packet_before_sending_the_next(self):
        self.replies = [GIF_NEXT, GIF_NEXT, GIF_FINISHED]
        order = []
        original_wait = self.under_test._wait_for_upload_status

        async def spy():
            order.append("wait")
            return await original_wait()

        self.under_test._wait_for_upload_status = spy
        self.client.write_gatt_char.side_effect = self._recording_write(order)

        await self.under_test.send_packets([[b"a"], [b"b"], [b"c"]], response=True, wait_for_ack=True)

        self.assertEqual(["write:a", "wait", "write:b", "wait", "write:c", "wait"], order)

    def _recording_write(self, order):
        original = self.client.write_gatt_char.side_effect

        async def write(char_specifier, data, response):
            order.append(f"write:{bytes(data).decode()}")
            await original(char_specifier=char_specifier, data=data, response=response)

        return write

    async def test_without_wait_for_ack_nothing_is_awaited(self):
        await self.under_test.send_packets([[b"a"], [b"b"]], response=True)

        self.assertEqual(2, self.client.write_gatt_char.await_count)

    async def test_never_reads_the_notification_characteristic(self):
        self.replies = [GIF_NEXT, GIF_FINISHED]

        await self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True)

        self.client.read_gatt_char.assert_not_awaited()

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
        write = self.client.write_gatt_char.side_effect

        async def write_with_noise(char_specifier, data, response):
            self.listener(None, bytearray(bytes.fromhex("0500040101")))
            await write(char_specifier=char_specifier, data=data, response=response)

        self.client.write_gatt_char.side_effect = write_with_noise

        await self.under_test.send_packets([[b"a"]], response=True, wait_for_ack=True)

    async def test_stale_notifications_are_discarded_before_an_upload(self):
        await self.under_test.connect()
        # a leftover from an earlier upload, which would be taken for the ack of the first packet
        self.listener(None, bytearray(GIF_FINISHED))
        self.replies = [GIF_NEXT, GIF_NEXT]

        await self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True)

        self.assertEqual(2, len(self.events))

    async def test_does_not_wait_if_notifications_are_not_available(self):
        self.client.start_notify.side_effect = RuntimeError("no notify")

        with patch("idotmatrix.connection_manager.UPLOAD_ACK_TIMEOUT_SECONDS", 0.05):
            await asyncio.wait_for(
                self.under_test.send_packets([[b"a"], [b"b"]], response=True, wait_for_ack=True), timeout=2)

        self.assertEqual(2, len(self.events))


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
        write = self.client.write_gatt_char.side_effect

        async def write_with_noise(char_specifier, data, response):
            self.listener(None, bytearray(bytes.fromhex("0500060100")))  # a rejection of ANOTHER command
            self.listener(None, bytearray(bytes.fromhex("0900018005090104")))  # something else entirely
            self.listener(None, bytearray(bytes.fromhex("0500048001")))
            await write(char_specifier=char_specifier, data=data, response=response)

        self.client.write_gatt_char.side_effect = write_with_noise

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

    async def test_stale_acks_are_discarded(self):
        await self.under_test.connect()
        self.listener(None, bytearray(bytes.fromhex("0500048000")))  # rejection of an earlier command
        self._answer_with(bytes.fromhex("0500048001"))

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

    async def test_a_missing_ack_is_only_logged(self):
        with patch("idotmatrix.connection_manager.COMMAND_ACK_TIMEOUT_SECONDS", 0.05):
            with self.assertLogs("idotmatrix.connection_manager", level="WARNING"):
                await self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True)

        self.assertEqual(1, len(self.events))

    async def test_does_not_wait_without_wait_for_ack(self):
        self._answer_with(bytes.fromhex("0500048000"))

        await self.under_test.send_bytes(self.BRIGHTNESS, response=True)

    async def test_does_not_wait_if_notifications_are_not_available(self):
        self.client.start_notify.side_effect = RuntimeError("no notify")

        await asyncio.wait_for(
            self.under_test.send_bytes(self.BRIGHTNESS, response=True, wait_for_ack=True), timeout=2)

        self.assertEqual(1, len(self.events))

    async def test_large_commands_are_written_completely_before_waiting_for_the_ack(self):
        self.under_test._max_ble_packet_size_override = 3
        self.reply_to_any_write = True
        self._answer_with(bytes.fromhex("0500048001"))

        await self.under_test.send_bytes(self.BRIGHTNESS, response=False, wait_for_ack=True)

        # both chunks were written, the single ack was found afterwards
        self.assertEqual(2, len(self.events))
