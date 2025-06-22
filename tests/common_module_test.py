from unittest.mock import AsyncMock

from idotmatrix.modules.common import CommonModule
from tests import TestBase


class TestCommonModule(TestBase):

    async def test_turn_on(self):
        # GIVEN
        connection_manager = AsyncMock()
        common_module = CommonModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await common_module.turn_on()

        # THEN
        # should be called:
        # self._connection_manager.send_bytes(data=data...)
        # and data should be:
        expected_data = bytearray(
            [5, 0, 7, 1, 1]
        )
        connection_manager.send_bytes.assert_awaited_once_with(data=expected_data, response=False, chunk_size=None)

    async def test_turn_off(self):
        # GIVEN
        connection_manager = AsyncMock()
        common_module = CommonModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await common_module.turn_off()

        # THEN
        # should be called:
        # self._connection_manager.send_bytes(data=data...)
        # and data should be:
        expected_data = bytearray(
            [5, 0, 7, 1, 0]
        )
        connection_manager.send_bytes.assert_awaited_once_with(data=expected_data, response=False, chunk_size=None)
