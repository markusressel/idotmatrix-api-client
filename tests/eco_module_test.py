from unittest.mock import AsyncMock

from idotmatrix.modules.eco import EcoModule
from tests import TestBase


class TestEcoModule(TestBase):

    async def test_show(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = EcoModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.set_mode(
            enabled=True,
            start_hour=2,
            start_minute=3,
            end_hour=4,
            end_minute=5,
            eco_brightness=255,
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\n\x00\x02\x80\x01\x02\x03\x04\x05\xff'),
            response=False,
        )
