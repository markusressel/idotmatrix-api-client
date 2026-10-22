from datetime import datetime
from unittest.mock import AsyncMock, patch

from idotmatrix.modules.common import CommonModule
from tests import TestBase


@patch("idotmatrix.modules.sleep", new=AsyncMock())
class TestCommonModule(TestBase):

    async def test_turn_on(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = CommonModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.turn_on()

        # THEN
        # should be called:
        # self._connection_manager.send_bytes(data=data...)
        # and data should be:
        expected_data = bytearray(
            [5, 0, 7, 1, 1]
        )
        connection_manager.send_bytes.assert_awaited_once_with(data=expected_data, response=False)

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
        connection_manager.send_bytes.assert_awaited_once_with(data=expected_data, response=True)

    def _module(self):
        self.connection_manager = AsyncMock()
        return CommonModule(connection_manager=self.connection_manager)

    def _assert_sent(self, data, response):
        self.connection_manager.send_bytes.assert_awaited_once_with(data=bytearray(data), response=response)

    async def test_freeze_screen(self):
        await self._module().freeze_screen()
        self._assert_sent([4, 0, 3, 0], True)

    async def test_set_screen_state(self):
        await self._module().set_screen_state(True)
        self._assert_sent([5, 0, 7, 1, 1], False)

    async def test_set_screen_state_off(self):
        await self._module().set_screen_state(False)
        self._assert_sent([5, 0, 7, 1, 0], False)

    async def test_set_screen_flipped(self):
        await self._module().set_screen_flipped()
        self._assert_sent([5, 0, 6, 128, 1], True)

    async def test_set_screen_not_flipped(self):
        await self._module().set_screen_flipped(False)
        self._assert_sent([5, 0, 6, 128, 0], True)

    async def test_set_brightness(self):
        await self._module().set_brightness(50)
        self._assert_sent([5, 0, 4, 128, 50], True)

    async def test_set_brightness_bounds(self):
        for value in (5, 100):
            with self.subTest(value=value):
                await self._module().set_brightness(value)

    async def test_set_brightness_out_of_range(self):
        for value in (-1, 0, 4, 101):
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self._module().set_brightness(value)

    async def test_set_speed(self):
        await self._module().set_speed(7)
        self._assert_sent([5, 0, 3, 1, 7], False)

    async def test_set_time(self):
        # 2025-01-06 is a Monday -> weekday 1
        await self._module().set_time(datetime(2025, 1, 6, 13, 14, 15))
        self._assert_sent([11, 0, 1, 128, 25, 1, 6, 1, 13, 14, 15], True)

    async def test_set_time_sunday_is_7(self):
        await self._module().set_time(datetime(2025, 1, 5, 0, 0, 0))
        self._assert_sent([11, 0, 1, 128, 25, 1, 5, 7, 0, 0, 0], True)

    async def test_set_joint(self):
        await self._module().set_joint(2)
        self._assert_sent([5, 0, 12, 128, 2], False)

    async def test_set_password(self):
        await self._module().set_password(123456)
        self._assert_sent([8, 0, 4, 2, 1, 12, 34, 56], False)

    async def test_set_password_leading_zeros(self):
        await self._module().set_password(1)
        self._assert_sent([8, 0, 4, 2, 1, 0, 0, 1], False)

    async def test_reset(self):
        module = self._module()
        await module.reset()
        self.connection_manager.send_packets.assert_awaited_once_with(
            packets=[[bytes([4, 0, 3, 128])]], response=True, wait_for_ack=False)
