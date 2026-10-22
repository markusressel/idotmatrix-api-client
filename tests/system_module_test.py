from unittest.mock import AsyncMock, patch

from idotmatrix.modules.system import SystemModule
from tests import TestBase


@patch("idotmatrix.modules.sleep", new=AsyncMock())
class TestSystemModule(TestBase):

    async def test_delete_device_data(self):
        connection_manager = AsyncMock()
        under_test = SystemModule(connection_manager=connection_manager)

        await under_test.delete_device_data()

        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray([17, 0, 2, 1, 12, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]),
            response=False,
        )

    async def test_get_device_location_sends_encrypted_payload(self):
        connection_manager = AsyncMock()
        under_test = SystemModule(connection_manager=connection_manager)

        await under_test.get_device_location()

        connection_manager.send_bytes.assert_awaited_once()
        data = connection_manager.send_bytes.await_args.kwargs["data"]
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 16)

    def test_encrypt_aes_roundtrip(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        encrypted = SystemModule._encrypt_aes(b"hello", key)
        self.assertEqual(b"hello", Fernet(key).decrypt(encrypted))
