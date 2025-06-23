from unittest.mock import AsyncMock

from idotmatrix.modules.graffiti import GraffitiModule
from tests import TestBase


class TestGraffitiModule(TestBase):

    async def test_upload_gif_file(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = GraffitiModule(
            connection_manager=connection_manager,
        )

        # WHEN
        await under_test.set_pixel(
            color=(1, 2, 3),
            xy=(4, 5)
        )

        # THEN
        connection_manager.send_bytes.assert_awaited_once_with(
            data=bytearray(b'\n\x00\x05\x01\x00\x01\x02\x03\x04\x05'),
            response=False,
            chunk_size=None,
        )
