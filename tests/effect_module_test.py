from unittest.mock import AsyncMock

from idotmatrix.modules.effect import EffectModule, EffectStyle
from tests import TestBase


class TestEffectModule(TestBase):

    async def test_show(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = EffectModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.show(
            style=EffectStyle.VERTICAL_RAINBOW,
            rgb_values=[
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255)
            ]
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\t\x00\x03\x02\x03Z\x03\xff\x00\x00\x00\xff\x00\x00\x00\xff'),
            response=False,
            chunk_size=None
        )
