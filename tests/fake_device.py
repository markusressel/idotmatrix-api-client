import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.const import UUID_READ_DATA
from tests import TestBase

ADDRESS = "00:11:22:33:44:55"


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
        self.auto_reply = None  # called with the written data, returns a notification or None

        async def connect():
            self.client.is_connected = True

        async def start_notify(uuid, callback):
            self.assertEqual(UUID_READ_DATA, uuid)
            self.listener = callback

        async def write(char_specifier, data, response):
            self.events.append(("write", bytes(data)))
            await asyncio.sleep(0)  # let other tasks run, like a real BLE write does
            # the device answers once a full protocol packet has been received
            if (response or self.reply_to_any_write) and self.replies:
                self.listener(None, bytearray(self.replies.pop(0)))
            elif self.auto_reply is not None:
                reply = self.auto_reply(bytes(data))
                if reply is not None:
                    self.listener(None, bytearray(reply))

        self.client.connect = AsyncMock(side_effect=connect)
        self.client.start_notify = AsyncMock(side_effect=start_notify)
        self.client.write_gatt_char = AsyncMock(side_effect=write)
        self.bleak_client_cls = bleak_client_cls
        bleak_client_cls.return_value = self.client

        self.under_test = ConnectionManager(address=ADDRESS)


