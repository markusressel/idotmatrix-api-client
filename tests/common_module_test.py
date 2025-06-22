from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules.common import CommonModule
from tests import TestBase


class TestCommonModule(TestBase):

    async def test_turn_on(self, tmp_path):
        # GIVEN
        connection_manager = ConnectionManager()
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
            [5, 0, 6, 1, 0]
        )
