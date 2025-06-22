from unittest.mock import AsyncMock

from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize
from tests import TestBase


class TestImageModule(TestBase):

    async def test_upload_image_file(self):
        # GIVEN
        connection_manager = AsyncMock()
        under_test = ImageModule(
            connection_manager=connection_manager,
            screen_size=ScreenSize.SIZE_64x64,
        )

        image_file_path = self._test_folder / "demo_64.png"

        # WHEN
        await under_test.upload_image_file(
            file_path=image_file_path.as_posix(),
        )

        # THEN
        connection_manager.send_packets.assert_awaited_once_with()
