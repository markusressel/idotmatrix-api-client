import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakDBusError

from idotmatrix.connection_manager import ConnectionListener, ConnectionManager
from idotmatrix.const import UUID_CHARACTERISTIC_WRITE_DATA, UUID_READ_DATA
from tests import TestBase

ADDRESS = "00:11:22:33:44:55"


def _fake_bleak_client(connected: bool = False, write_size: int = 514) -> MagicMock:
    client = MagicMock()
    client.is_connected = connected
    client.mtu_size = None
    client._backend = MagicMock(spec=[])
    client.services = MagicMock()
    client.services.__iter__.return_value = iter([])
    client.services.get_characteristic.return_value.max_write_without_response_size = write_size

    async def connect():
        client.is_connected = True

    client.connect = AsyncMock(side_effect=connect)
    client.disconnect = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"ok")
    return client


class TestConnectionManager(TestBase):

    def setUp(self):
        patcher = patch("idotmatrix.connection_manager.BleakClient")
        self.bleak_client_cls = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = _fake_bleak_client()
        self.bleak_client_cls.return_value = self.client

    async def test_set_address_creates_client(self):
        under_test = ConnectionManager(address=ADDRESS)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertIs(self.client, under_test.client)
        self.bleak_client_cls.assert_called_once()
        self.assertEqual(ADDRESS, self.bleak_client_cls.call_args.kwargs["address_or_ble_device"])

    async def test_create_ble_client_without_address_raises(self):
        under_test = ConnectionManager()
        with self.assertRaises(ValueError):
            under_test._create_ble_client()

    async def test_is_connected_without_client(self):
        self.assertFalse(ConnectionManager().is_connected())

    async def test_connect(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.connect()

        self.client.connect.assert_awaited_once()
        self.assertTrue(under_test.is_connected())

    async def test_connect_when_already_connected_does_not_reconnect(self):
        under_test = ConnectionManager(address=ADDRESS)
        await under_test.connect()

        await under_test.connect()

        self.client.connect.assert_awaited_once()

    async def test_connect_notifies_listeners(self):
        under_test = ConnectionManager(address=ADDRESS)
        on_connected = AsyncMock()
        under_test.add_connection_listener(ConnectionListener(on_connected=on_connected, on_disconnected=None))

        await under_test.connect()
        await asyncio.sleep(0)

        on_connected.assert_awaited_once()

    async def test_connect_when_already_connected_does_not_notify_again(self):
        under_test = ConnectionManager(address=ADDRESS)
        on_connected = AsyncMock()
        under_test.add_connection_listener(ConnectionListener(on_connected=on_connected, on_disconnected=None))
        await under_test.connect()

        await under_test.connect()
        await asyncio.sleep(0)

        on_connected.assert_awaited_once()

    async def test_connect_without_address_uses_discovery(self):
        under_test = ConnectionManager()
        under_test.discover_devices = AsyncMock(return_value=[ADDRESS])

        await asyncio.wait_for(under_test.connect(), timeout=2)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertTrue(under_test.is_connected())

    async def test_connect_by_discovery_no_devices(self):
        under_test = ConnectionManager()
        under_test.discover_devices = AsyncMock(return_value=[])

        with self.assertRaises(AssertionError):
            await under_test.connect_by_discovery()

    async def test_connect_by_address(self):
        under_test = ConnectionManager()

        await under_test.connect_by_address(ADDRESS)

        self.assertEqual(ADDRESS, under_test.address)
        self.assertTrue(under_test.is_connected())

    async def test_disconnect(self):
        under_test = ConnectionManager(address=ADDRESS)
        await under_test.connect()

        await under_test.disconnect()

        self.client.disconnect.assert_awaited_once()
        self.assertFalse(under_test._connected)

    async def test_disconnect_when_not_connected(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.disconnect()

        self.client.disconnect.assert_not_awaited()

    async def test_disconnect_cancels_reconnect_task(self):
        under_test = ConnectionManager(address=ADDRESS)
        task = asyncio.create_task(asyncio.sleep(60))
        under_test._reconnect_loop_task = task

        await under_test.disconnect()
        await asyncio.sleep(0)

        self.assertTrue(task.cancelled())
        self.assertIsNone(under_test._reconnect_loop_task)

    async def test_send_bytes_connects_if_needed(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_bytes(b"\x01\x02")

        self.client.connect.assert_awaited_once()

    async def test_send_bytes_single_chunk(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_bytes(b"\x01\x02\x03")

        self.client.write_gatt_char.assert_awaited_once_with(
            char_specifier=UUID_CHARACTERISTIC_WRITE_DATA, data=b"\x01\x02\x03", response=False)

    async def test_send_bytes_splits_into_chunks(self):
        self.client = _fake_bleak_client(write_size=50)
        self.bleak_client_cls.return_value = self.client
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_bytes(bytes(range(120)))

        sent = [c.kwargs["data"] for c in self.client.write_gatt_char.await_args_list]
        self.assertEqual([bytes(range(50)), bytes(range(50, 100)), bytes(range(100, 120))], sent)

    async def test_send_bytes_with_response_uses_512_chunks(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_bytes(bytes(1100), response=True)

        sizes = [len(c.kwargs["data"]) for c in self.client.write_gatt_char.await_args_list]
        self.assertEqual([512, 512, 76], sizes)
        self.assertTrue(all(c.kwargs["response"] for c in self.client.write_gatt_char.await_args_list))

    async def test_send_bytes_empty_data_sends_nothing(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_bytes(b"")

        self.client.write_gatt_char.assert_not_awaited()

    async def test_max_bytes_default_when_device_reports_20(self):
        self.client = _fake_bleak_client(write_size=20)
        self.bleak_client_cls.return_value = self.client
        under_test = ConnectionManager(address=ADDRESS)
        await under_test.connect()

        self.assertEqual(514, await under_test.get_max_bytes_per_chunk(response=False))

    async def test_send_packets_empty_is_noop(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_packets([])

        self.client.connect.assert_not_awaited()
        self.client.write_gatt_char.assert_not_awaited()

    async def test_send_packets_response_only_on_last_chunk_of_packet(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_packets([[b"a", b"b"], [b"c"]], response=True)

        calls = [(c.kwargs["data"], c.kwargs["response"]) for c in self.client.write_gatt_char.await_args_list]
        self.assertEqual([(b"a", False), (b"b", True), (b"c", True)], calls)
        self.assertEqual(2, self.client.read_gatt_char.await_count)
        self.client.read_gatt_char.assert_awaited_with(UUID_READ_DATA)

    async def test_send_packets_without_response_never_reads(self):
        under_test = ConnectionManager(address=ADDRESS)

        await under_test.send_packets([[b"a", b"b"]], response=False)

        self.client.read_gatt_char.assert_not_awaited()

    async def test_send_packets_survives_read_errors(self):
        under_test = ConnectionManager(address=ADDRESS)
        self.client.read_gatt_char.side_effect = [
            BleakDBusError("org.bluez.Error.NotPermitted", []),
            BleakDBusError("org.bluez.Error.Failed", []),
            RuntimeError("boom"),
        ]

        await under_test.send_packets([[b"a"], [b"b"], [b"c"]], response=True)

        self.assertEqual(3, self.client.write_gatt_char.await_count)

    async def test_read_returns_data(self):
        under_test = ConnectionManager(address=ADDRESS)
        await under_test.connect()

        self.assertEqual(b"ok", await under_test.read())

    async def test_on_disconnected_notifies_listeners(self):
        under_test = ConnectionManager(address=ADDRESS)
        on_disconnected = AsyncMock()
        under_test.add_connection_listener(ConnectionListener(on_connected=None, on_disconnected=on_disconnected))
        await under_test.connect()
        self.client.is_connected = False

        under_test._on_disconnected(self.client)
        await asyncio.sleep(0)

        on_disconnected.assert_awaited_once()
        self.assertFalse(under_test._connected)

    async def test_on_disconnected_starts_reconnect_loop_when_enabled(self):
        under_test = ConnectionManager(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        await under_test.connect()
        self.client.is_connected = False

        with patch.object(under_test, "_reconnect_loop", new=AsyncMock()) as loop:
            under_test._on_disconnected(self.client)
            await asyncio.sleep(0)

        loop.assert_awaited_once()

    async def test_on_disconnected_no_reconnect_when_disabled(self):
        under_test = ConnectionManager(address=ADDRESS)
        await under_test.connect()
        self.client.is_connected = False

        under_test._on_disconnected(self.client)

        self.assertIsNone(under_test._reconnect_loop_task)

    async def test_reconnect_loop_reconnects(self):
        under_test = ConnectionManager(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        with patch("idotmatrix.connection_manager.asyncio.sleep", new=AsyncMock()):
            await under_test._reconnect_loop()

        self.assertTrue(under_test.is_connected())

    async def test_reconnect_loop_retries_after_failure(self):
        under_test = ConnectionManager(address=ADDRESS)
        under_test.set_auto_reconnect(True)
        calls = []

        async def connect():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("fail")
            self.client.is_connected = True

        self.client.connect = AsyncMock(side_effect=connect)
        with patch("idotmatrix.connection_manager.asyncio.sleep", new=AsyncMock()):
            await under_test._reconnect_loop()

        self.assertEqual(2, len(calls))

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
                with patch("idotmatrix.connection_manager.BleakClient"):
                    ConnectionManager(address=ADDRESS)
            except Exception as e:
                errors.append(e)

        thread = threading.Thread(target=construct)
        thread.start()
        thread.join()

        self.assertEqual([], errors)
