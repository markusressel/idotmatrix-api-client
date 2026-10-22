from unittest.mock import AsyncMock, patch

from idotmatrix.modules import IDotMatrixModule
from tests import TestBase


class TestModuleBase(TestBase):

    def setUp(self):
        self.connection_manager = AsyncMock()
        self.connection_manager.send_bytes.return_value = False
        self.under_test = IDotMatrixModule(connection_manager=self.connection_manager)
        patcher = patch("idotmatrix.modules.sleep", new_callable=AsyncMock)
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    async def test_sleeps_after_commands_without_response(self):
        await self.under_test._send_bytes(b"abcde")

        self.sleep.assert_awaited_once_with(0.5)
        self.connection_manager.send_bytes.assert_awaited_once_with(data=b"abcde", response=False)

    async def test_does_not_sleep_after_commands_with_response(self):
        await self.under_test._send_bytes(b"abcde", response=True)

        self.sleep.assert_not_awaited()

    async def test_does_not_sleep_after_acknowledged_commands(self):
        # the acknowledgement tells that the device is done with the command
        self.connection_manager.send_bytes.return_value = True

        await self.under_test._send_bytes(b"abcde")

        self.sleep.assert_not_awaited()

    async def test_sleep_after_is_respected(self):
        self.connection_manager.send_bytes.return_value = True

        await self.under_test._send_bytes(b"abcde", sleep_after=0.1)

        self.sleep.assert_awaited_once_with(0.1)
