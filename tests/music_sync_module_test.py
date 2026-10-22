from unittest.mock import AsyncMock, patch

from idotmatrix.modules.music_sync import MusicSyncModule
from tests import TestBase


@patch("idotmatrix.modules.sleep", new=AsyncMock())
class TestMusicSyncModule(TestBase):

    def setUp(self):
        self.connection_manager = AsyncMock()
        self.under_test = MusicSyncModule(connection_manager=self.connection_manager)

    async def test_set_mic_type(self):
        await self.under_test.set_mic_type(3)
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray([6, 0, 11, 128, 3]), response=False)

    async def test_set_mic_type_wraps_at_256(self):
        await self.under_test.set_mic_type(257)
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray([6, 0, 11, 128, 1]), response=False)

    async def test_send_image_rythm(self):
        await self.under_test.send_image_rythm(5)
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray([6, 0, 0, 2, 5, 1]), response=False)

    async def test_send_rhythm_forwards_raw_data(self):
        payload = bytearray([1, 2, 3])
        await self.under_test.send_rhythm(mode=1, byteArray=payload)
        self.connection_manager.send_bytes.assert_awaited_once_with(data=payload, response=False)

    async def test_stop_rythm(self):
        await self.under_test.stop_rythm()
        self.connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray([6, 0, 0, 2, 0, 0]), response=False)
