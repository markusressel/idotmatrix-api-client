from unittest.mock import AsyncMock

from idotmatrix.modules.fullscreen_color import FullscreenColorModule
from tests import TestBase


class TestFullscreenColorModule(TestBase):

    async def test_set_color_red(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = FullscreenColorModule(
            connection_manager=connection_manager,
        )
        color = (255, 0, 0)  # Red color

        # WHEN
        await under_test.show_color(
            color=color
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x02\x02\xff\x00\x00'),
            response=True,
            chunk_size=None
        )

    async def test_set_color_green(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = FullscreenColorModule(
            connection_manager=connection_manager,
        )
        color = (0, 255, 0)

        # WHEN
        await under_test.show_color(
            color=color
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x02\x02\x00\xff\x00'),
            response=True,
            chunk_size=None
        )

    async def test_set_color_blue(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = FullscreenColorModule(
            connection_manager=connection_manager,
        )
        color = (0, 0, 255)

        # WHEN
        await under_test.show_color(
            color=color
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x07\x00\x02\x02\x00\x00\xff'),
            response=True,
            chunk_size=None
        )
