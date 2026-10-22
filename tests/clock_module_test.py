from unittest.mock import AsyncMock

from idotmatrix.modules.clock import ClockModule, ClockStyle
from tests import TestBase


class TestClockModule(TestBase):

    async def test_show(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ClockModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.show()

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x08\x00\x06\x01\xc0\xff\xff\xff'),
            response=False,
        )

    async def test_show_with_style(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ClockModule(
            connection_manager=connection_manager,
        )
        style = ClockStyle.RGBSwipeOutline

        # WHEN
        await under_test.show(style=style)

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x08\x00\x06\x01\xc0\xff\xff\xff'),
            response=False,
        )

    async def test_show_with_custom_color(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ClockModule(
            connection_manager=connection_manager,
        )
        color = (123, 234, 45)

        # WHEN
        await under_test.show(color=color)

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x08\x00\x06\x01\xc0{\xea-'),
            response=False,
        )

    async def test_show_without_date(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ClockModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.show(show_date=False)

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x08\x00\x06\x01@\xff\xff\xff'),
            response=False,
        )

    async def test_show_with_12_hour_format(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ClockModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.show(hour24=False)

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\x08\x00\x06\x01\x80\xff\xff\xff'),
            response=False,
        )
