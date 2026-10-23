import asyncio
from unittest.mock import AsyncMock, patch

from idotmatrix.connection_manager import ConnectionListener
from tests.fake_device import FakeDeviceTestBase

# a brightness that is out of range: the device rejects it (status 0), so nothing changes, but it proves that it is alive
PING = bytes([5, 0, 4, 128, 255])
ALIVE = bytes.fromhex("0500048000")


class TestHeartbeat(FakeDeviceTestBase):

    def setUp(self):
        super().setUp()
        self.transport.auto_reply = lambda data: ALIVE if data == PING else None
        patcher = patch("idotmatrix.connection_manager.HEARTBEAT_ACK_TIMEOUT_SECONDS", 0.1)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._stop)

    def _stop(self):
        task = self.under_test._heartbeat_task
        if task:
            task.cancel()
        reconnect = self.under_test._reconnect_loop_task
        if reconnect:
            reconnect.cancel()

    def _pings(self):
        return [event for event in self.events if event == ("write", PING)]

    async def test_there_is_no_heartbeat_by_default(self):
        await self.under_test.connect()

        await asyncio.sleep(0.3)

        self.assertEqual([], self.events)

    async def test_pings_while_idle(self):
        self.under_test.set_heartbeat(0.1)
        await self.under_test.connect()

        await asyncio.sleep(0.45)

        self.assertGreaterEqual(len(self._pings()), 2)

    async def test_a_rejected_ping_means_that_the_device_is_alive(self):
        self.under_test.set_heartbeat(0.1)
        await self.under_test.connect()

        await asyncio.sleep(0.45)

        self.transport.disconnect.assert_not_awaited()
        self.assertTrue(self.under_test.is_connected())

    async def test_notifications_count_as_activity(self):
        self.under_test.set_heartbeat(0.2)
        await self.under_test.connect()

        for _ in range(8):
            self.transport.notify(b"\x05\x00\x06\x01\x01")
            await asyncio.sleep(0.05)

        self.assertEqual([], self._pings())

    async def test_a_dead_link_is_closed_and_reported(self):
        self.transport.auto_reply = None
        on_disconnected = AsyncMock()
        self.under_test.add_connection_listener(ConnectionListener(on_connected=None, on_disconnected=on_disconnected))
        self.under_test.set_heartbeat(0.1)
        await self.under_test.connect()

        await asyncio.sleep(0.6)

        self.transport.disconnect.assert_awaited_once()
        on_disconnected.assert_awaited_once()
        self.assertFalse(self.under_test._connected)
        self.assertEqual(1, len(self._pings()))  # no more pings once the link is closed

    async def test_a_dead_link_is_replaced_by_a_new_client_when_reconnecting(self):
        answers = {"alive": False}
        self.transport.auto_reply = lambda data: ALIVE if data == PING and answers["alive"] else None
        self.under_test.set_auto_reconnect(True)
        self.under_test.set_heartbeat(0.1)
        with patch("idotmatrix.connection_manager.RECONNECT_INITIAL_DELAY_SECONDS", 0.05):
            await self.under_test.connect()
            # the old client keeps claiming to be connected, as the link died silently, until it is told to disconnect
            self.transport.is_connected = True

            async def disconnect():
                self.transport.is_connected = False

            self.transport.disconnect.side_effect = disconnect
            clients_before = len(self.transports)

            await asyncio.sleep(0.45)
            answers["alive"] = True
            await asyncio.sleep(0.5)

        self.assertGreater(len(self.transports), clients_before)
        self.assertGreaterEqual(self.transport.connect.await_count, 2)

    async def test_a_failing_write_means_that_the_link_is_dead(self):
        write = self.transport.write.side_effect

        async def failing_write(char_specifier, data, response):
            if bytes(data) == PING:
                raise OSError("link lost")
            await write(char_specifier=char_specifier, data=data, response=response)

        self.transport.write.side_effect = failing_write
        self.under_test.set_heartbeat(0.1)
        await self.under_test.connect()

        await asyncio.sleep(0.4)

        self.transport.disconnect.assert_awaited_once()

    async def test_stops_when_disconnecting(self):
        self.under_test.set_heartbeat(0.1)
        await self.under_test.connect()
        await asyncio.sleep(0.25)
        await self.under_test.disconnect()
        pings = len(self._pings())

        await asyncio.sleep(0.4)

        self.assertEqual(pings, len(self._pings()))

    async def test_can_be_enabled_while_connected(self):
        await self.under_test.connect()

        self.under_test.set_heartbeat(0.1)
        await asyncio.sleep(0.35)

        self.assertGreaterEqual(len(self._pings()), 1)

    async def test_can_be_disabled_while_connected(self):
        self.under_test.set_heartbeat(0.1)
        await self.under_test.connect()
        await asyncio.sleep(0.25)
        self.under_test.set_heartbeat(None)
        pings = len(self._pings())

        await asyncio.sleep(0.4)

        self.assertEqual(pings, len(self._pings()))

    async def test_rejects_invalid_intervals(self):
        for interval in (0, -1):
            with self.subTest(interval=interval), self.assertRaises(ValueError):
                self.under_test.set_heartbeat(interval)

    async def test_is_not_started_without_notifications(self):
        # without acknowledgements there is nothing to wait for
        self.transport.start_notify.side_effect = RuntimeError("no notify")
        self.under_test.set_heartbeat(0.1)

        await self.under_test.connect()
        await asyncio.sleep(0.3)

        self.assertEqual([], self._pings())


class TestSerializedWrites(FakeDeviceTestBase):

    async def test_concurrent_commands_do_not_interleave_their_chunks(self):
        self.under_test._max_ble_packet_size_override = 2

        await asyncio.gather(
            self.under_test.send_bytes(b"aaaaaa", wait_for_ack=False),
            self.under_test.send_bytes(b"bbbbbb", wait_for_ack=False),
        )

        self.assertEqual(
            [b"aa", b"aa", b"aa", b"bb", b"bb", b"bb"],
            [data for _, data in self.events],
        )

    async def test_concurrent_uploads_do_not_interleave_their_packets(self):
        await asyncio.gather(
            self.under_test.send_packets([[b"a1", b"a2"], [b"a3"]]),
            self.under_test.send_packets([[b"b1"], [b"b2", b"b3"]]),
        )

        self.assertEqual(
            [b"a1", b"a2", b"a3", b"b1", b"b2", b"b3"],
            [data for _, data in self.events],
        )
