from unittest.mock import AsyncMock

from idotmatrix.modules.chronograph import ChronographModule
from tests import TestBase


class TestChronographModule(TestBase):

    async def test_reset(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ChronographModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.reset()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x05\x00\t\x80\x00'),
            response=False,
        )

    async def test_start_from_zero(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ChronographModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.start_from_zero()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x05\x00\t\x80\x01'),
            response=False,
        )

    async def test_pause(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ChronographModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.pause()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x05\x00\t\x80\x02'),
            response=False,
        )

    async def test_resume(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ChronographModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.resume()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x05\x00\t\x80\x03'),
            response=False,
        )
