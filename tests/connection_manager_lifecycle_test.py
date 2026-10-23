import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from idotmatrix.connection_manager import ConnectionListener, ConnectionManager
from tests import TestBase
from tests.fake_transport import FakeTransport

ADDRESS = "00:11:22:33:44:55"


class TestConnectionManager(TestBase):

    def setUp(self):
        self.transport = FakeTransport()
        self.created_for = []  # the address of every transport that was created

        def factory(address, on_disconnected):
            self.created_for.append(address)
            self.transport.address = address
            self.transport.on_disconnected = on_disconnected
            return self.transport

        self.factory = factory

    def create(self, address=None):
        return ConnectionManager(address=address, transport_factory=self.factory)

    async def test_set_address_creates_a_transport(self):
        under_test = self.create(address=ADDRESS)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertEqual([ADDRESS], self.created_for)

    async def test_set_address_to_another_address_creates_a_new_transport(self):
        under_test = self.create(address=ADDRESS)

        under_test.set_address("AA:BB:CC:DD:EE:FF")

        self.assertEqual([ADDRESS, "AA:BB:CC:DD:EE:FF"], self.created_for)

    async def test_set_address_to_the_same_address_keeps_the_transport(self):
        under_test = self.create(address=ADDRESS)

        under_test.set_address(ADDRESS)

        self.assertEqual([ADDRESS], self.created_for)

    async def test_set_device_creates_a_transport_for_the_device(self):
        under_test = self.create()
        device = MagicMock(address=ADDRESS)

        under_test.set_device(device)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertEqual([device], self.created_for)

    async def test_set_device_with_a_newer_device_creates_a_new_transport(self):
        under_test = self.create()
        first, second = MagicMock(address=ADDRESS), MagicMock(address=ADDRESS)

        under_test.set_device(first)
        under_test.set_device(second)

        self.assertEqual([first, second], self.created_for)

    async def test_set_device_does_not_interrupt_a_connection(self):
        under_test = self.create()
        first, second = MagicMock(address=ADDRESS), MagicMock(address=ADDRESS)
        under_test.set_device(first)
        await under_test.connect()

        under_test.set_device(second)

        self.assertTrue(under_test.is_connected())
        self.assertEqual([first], self.created_for)

    async def test_the_newer_device_is_used_for_the_next_connection(self):
        under_test = self.create()
        first, second = MagicMock(address=ADDRESS), MagicMock(address=ADDRESS)
        under_test.set_device(first)
        await under_test.connect()
        under_test.set_device(second)
        self.transport.lose_connection()
        under_test._connected = False

        await under_test.connect()

        self.assertEqual([first, second], self.created_for)
        self.assertTrue(under_test.is_connected())

    async def test_a_dead_link_is_replaced_by_a_transport_for_the_same_device(self):
        under_test = self.create()
        device = MagicMock(address=ADDRESS)
        under_test.set_device(device)
        await under_test.connect()

        await under_test._close_dead_link()

        self.assertEqual([device, device], self.created_for)

    async def test_create_transport_without_address_raises(self):
        under_test = self.create()
        with self.assertRaises(ValueError):
            under_test._create_transport()

    async def test_is_connected_without_transport(self):
        self.assertFalse(self.create().is_connected())

    async def test_connect(self):
        under_test = self.create(address=ADDRESS)

        await under_test.connect()

        self.transport.connect.assert_awaited_once()
        self.assertTrue(under_test.is_connected())

    async def test_connect_when_already_connected_does_not_reconnect(self):
        under_test = self.create(address=ADDRESS)
        await under_test.connect()

        await under_test.connect()

        self.transport.connect.assert_awaited_once()

    async def test_connect_notifies_listeners(self):
        under_test = self.create(address=ADDRESS)
        on_connected = AsyncMock()
        under_test.add_connection_listener(ConnectionListener(on_connected=on_connected, on_disconnected=None))

        await under_test.connect()
        await asyncio.sleep(0)

        on_connected.assert_awaited_once()

    async def test_connect_when_already_connected_does_not_notify_again(self):
        under_test = self.create(address=ADDRESS)
        on_connected = AsyncMock()
        under_test.add_connection_listener(ConnectionListener(on_connected=on_connected, on_disconnected=None))
        await under_test.connect()

        await under_test.connect()
        await asyncio.sleep(0)

        on_connected.assert_awaited_once()

    async def test_connect_without_address_uses_discovery(self):
        under_test = self.create()
        under_test.discover_devices = AsyncMock(return_value=[ADDRESS])

        await asyncio.wait_for(under_test.connect(), timeout=2)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertTrue(under_test.is_connected())

    async def test_connect_of_one_manager_is_not_blocked_by_another(self):
        first = self.create(address=ADDRESS)
        second = self.create(address=ADDRESS)

        async with first._lock:
            await asyncio.wait_for(second.connect(), timeout=2)

        self.assertTrue(second.is_connected())

    async def test_connect_by_discovery_no_devices(self):
        under_test = self.create()
        under_test.discover_devices = AsyncMock(return_value=[])

        with self.assertRaises(AssertionError):
            await under_test.connect_by_discovery()

    async def test_connect_by_address(self):
        under_test = self.create()

        await under_test.connect_by_address(ADDRESS)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertTrue(under_test.is_connected())

    async def test_disconnect(self):
        under_test = self.create(address=ADDRESS)
        await under_test.connect()

        await under_test.disconnect()

        self.transport.disconnect.assert_awaited_once()
        self.assertFalse(under_test._connected)

    async def test_disconnect_when_not_connected(self):
        under_test = self.create(address=ADDRESS)

        await under_test.disconnect()

        self.transport.disconnect.assert_not_awaited()

    async def test_disconnect_cancels_reconnect_task(self):
        under_test = self.create(address=ADDRESS)
        task = asyncio.create_task(asyncio.sleep(60))
        under_test._reconnect_loop_task = task

        await under_test.disconnect()
        await asyncio.sleep(0)

        self.assertTrue(task.cancelled())
        self.assertIsNone(under_test._reconnect_loop_task)

    async def test_send_bytes_connects_if_needed(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_bytes(b"\x01\x02")

        self.transport.connect.assert_awaited_once()

    async def test_send_bytes_single_chunk(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_bytes(b"\x01\x02\x03")

        self.transport.write.assert_awaited_once_with(b"\x01\x02\x03", response=False)

    async def test_send_bytes_splits_into_chunks(self):
        self.transport.max_size = 50
        under_test = self.create(address=ADDRESS)

        await under_test.send_bytes(bytes(range(120)))

        sent = [c.args[0] for c in self.transport.write.await_args_list]
        self.assertEqual([bytes(range(50)), bytes(range(50, 100)), bytes(range(100, 120))], sent)

    async def test_send_bytes_with_response_uses_512_chunks(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_bytes(bytes(1100), response=True)

        sizes = [len(c.args[0]) for c in self.transport.write.await_args_list]
        self.assertEqual([512, 512, 76], sizes)
        self.assertTrue(all(c.kwargs["response"] for c in self.transport.write.await_args_list))

    async def test_send_bytes_empty_data_sends_nothing(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_bytes(b"")

        self.transport.write.assert_not_awaited()

    async def test_max_bytes_comes_from_the_transport(self):
        self.transport.max_size = 514  # a transport reports its best guess itself, see transport_test.py
        under_test = self.create(address=ADDRESS)
        await under_test.connect()

        self.assertEqual(514, await under_test.get_max_bytes_per_chunk(response=False))

    async def test_send_packets_empty_is_noop(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_packets([])

        self.transport.connect.assert_not_awaited()
        self.transport.write.assert_not_awaited()

    async def test_send_packets_response_only_on_last_chunk_of_packet(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_packets([[b"a", b"b"], [b"c"]], response=True)

        calls = [(c.args[0], c.kwargs["response"]) for c in self.transport.write.await_args_list]
        self.assertEqual([(b"a", False), (b"b", True), (b"c", True)], calls)
        # fa03 only supports notifications, reading it is always rejected
        self.transport.read.assert_not_awaited()

    async def test_send_packets_without_response_never_reads(self):
        under_test = self.create(address=ADDRESS)

        await under_test.send_packets([[b"a", b"b"]], response=False)

        self.transport.read.assert_not_awaited()

    async def test_read_returns_data(self):
        under_test = self.create(address=ADDRESS)
        await under_test.connect()

        self.assertEqual(b"ok", await under_test.read())

    async def test_on_disconnected_notifies_listeners(self):
        under_test = self.create(address=ADDRESS)
        on_disconnected = AsyncMock()
        under_test.add_connection_listener(ConnectionListener(on_connected=None, on_disconnected=on_disconnected))
        await under_test.connect()
        self.transport.is_connected = False

        under_test._on_disconnected()
        await asyncio.sleep(0)

        on_disconnected.assert_awaited_once()
        self.assertFalse(under_test._connected)

    async def test_on_disconnected_starts_reconnect_loop_when_enabled(self):
        under_test = self.create(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        await under_test.connect()
        self.transport.is_connected = False

        with patch.object(under_test, "_reconnect_loop", new=AsyncMock()) as loop:
            under_test._on_disconnected()
            await asyncio.sleep(0)

        loop.assert_awaited_once()

    async def test_on_disconnected_no_reconnect_when_disabled(self):
        under_test = self.create(address=ADDRESS)
        await under_test.connect()
        self.transport.is_connected = False

        under_test._on_disconnected()

        self.assertIsNone(under_test._reconnect_loop_task)

    async def test_reconnect_loop_reconnects(self):
        under_test = self.create(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        with patch("idotmatrix.connection_manager.asyncio.sleep", new=AsyncMock()):
            await under_test._reconnect_loop()

        self.assertTrue(under_test.is_connected())

    async def test_reconnect_loop_retries_after_failure(self):
        under_test = self.create(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        calls = []

        async def connect():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("fail")
            self.transport.is_connected = True

        self.transport.connect = AsyncMock(side_effect=connect)
        with patch("idotmatrix.connection_manager.asyncio.sleep", new=AsyncMock()):
            await under_test._reconnect_loop()

        self.assertEqual(2, len(calls))

    async def test_reconnect_loop_backs_off_and_caps_the_delay(self):
        under_test = self.create(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        calls = []

        async def connect():
            calls.append(1)
            if len(calls) <= 7:
                raise RuntimeError("fail")
            self.transport.is_connected = True

        self.transport.connect = AsyncMock(side_effect=connect)
        sleep = AsyncMock()
        with patch("idotmatrix.connection_manager.asyncio.sleep", new=sleep):
            await under_test._reconnect_loop()

        self.assertEqual([5, 10, 20, 40, 60, 60, 60, 60], [c.args[0] for c in sleep.await_args_list])

    async def test_reconnect_loop_starts_with_the_initial_delay_again(self):
        under_test = self.create(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        sleep = AsyncMock()
        with patch("idotmatrix.connection_manager.asyncio.sleep", new=sleep):
            await under_test._reconnect_loop()
            self.transport.is_connected = False
            under_test._connected = False
            await under_test._reconnect_loop()

        self.assertEqual([5, 5], [c.args[0] for c in sleep.await_args_list])

    async def test_send_bytes_logs_the_correct_chunk_count(self):
        under_test = self.create(address=ADDRESS)
        await under_test.connect()

        with self.assertLogs("idotmatrix.connection_manager", level="DEBUG") as logs:
            # exactly two full chunks
            await under_test.send_bytes(bytes(2 * 514))

        messages = [r.getMessage() for r in logs.records if r.getMessage().startswith("sending chunk")]
        self.assertEqual(["sending chunk 1 of 2", "sending chunk 2 of 2"], messages)

    async def test_discover_devices_logs_with_the_module_logger(self):
        with patch("idotmatrix.connection_manager.BleakScanner.discover", new=AsyncMock(return_value={})):
            with self.assertLogs("idotmatrix.connection_manager", level="INFO"):
                await ConnectionManager.discover_devices()

    async def test_discover_devices_filters_by_name(self):
        from bleak import AdvertisementData
        idm = MagicMock(address="AA")
        other = MagicMock(address="BB")
        adv_idm = MagicMock(spec=AdvertisementData, local_name="IDM-1234")
        adv_other = MagicMock(spec=AdvertisementData, local_name="Headphones")
        adv_none = MagicMock(spec=AdvertisementData, local_name=None)
        found = {"AA": (idm, adv_idm), "BB": (other, adv_other), "CC": (other, adv_none)}

        with patch("idotmatrix.connection_manager.BleakScanner.discover", new=AsyncMock(return_value=found)):
            self.assertEqual(["AA"], await ConnectionManager.discover_devices())


class TestConnectionManagerConstruction(unittest.TestCase):

    def test_construct_without_running_loop(self):
        """Constructing a client in plain sync code (no event loop) must work."""
        errors = []

        def construct():
            try:
                with patch("idotmatrix.transport.BleakClient"):
                    ConnectionManager(address=ADDRESS)
            except Exception as e:
                errors.append(e)

        thread = threading.Thread(target=construct)
        thread.start()
        thread.join()

        self.assertEqual([], errors)


class TestSignalHandlers(unittest.IsolatedAsyncioTestCase):

    async def test_installed_by_default(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "add_signal_handler") as add_signal_handler:
            ConnectionManager(transport_factory=lambda address, on_disconnected: FakeTransport())

        self.assertEqual(2, add_signal_handler.call_count)

    async def test_can_be_turned_off(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "add_signal_handler") as add_signal_handler:
            ConnectionManager(
                transport_factory=lambda address, on_disconnected: FakeTransport(), install_signal_handlers=False)

        add_signal_handler.assert_not_called()
