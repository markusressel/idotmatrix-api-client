from unittest.mock import AsyncMock

from idotmatrix.modules.countdown import CountdownModule
from tests import TestBase


class TestCountdownModule(TestBase):

    async def test_start(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = CountdownModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.start(minutes=5, seconds=30)

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x08\x80\x01\x05\x1e'),
            response=False,
            chunk_size=None
        )

    async def test_stop(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = CountdownModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.stop()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x08\x80\x00\x00\x00'),
            response=False,
            chunk_size=None
        )

    async def test_restart(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = CountdownModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.restart()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x08\x80\x03\x00\x00'),
            response=False,
            chunk_size=None
        )

    async def test_pause(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = CountdownModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.pause()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x08\x80\x02\x00\x00'),
            response=False,
            chunk_size=None
        )
