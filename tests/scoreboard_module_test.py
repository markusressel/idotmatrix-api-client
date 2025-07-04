from unittest.mock import AsyncMock

from idotmatrix.modules.scoreboard import ScoreboardModule
from tests import TestBase


class TestScoreboardModule(TestBase):

    async def test_show(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ScoreboardModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.show(
            count1=10,
            count2=25,
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x08\x00\n\x80\n\x00\x19\x00'),
            response=False,
        )
