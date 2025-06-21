from typing import Optional

from idotmatrix.connectionManager import ConnectionManager
from idotmatrix.modules.image import ImageModule
from idotmatrix.screensize import ScreenSize


class IDotMatrixClient:

    def __init__(
        self,
        screen_size: ScreenSize,
        mac_address: Optional[str] = None,
    ):
        self._connection_manager = ConnectionManager()
        self._connection_manager.address = mac_address
        self._screen_size = screen_size
        self._mac_address = mac_address

    @property
    def image(self) -> ImageModule:
        return ImageModule(
            connection_manager=self._connection_manager,
            screen_size=self._screen_size
        )

    async def connect(self):
        """
        Connect to the IDotMatrix server.
        """
        if self._mac_address:
            await self._connection_manager.connect_by_address(self._mac_address)
        else:
            await self._connection_manager.connect_by_search()

    async def disconnect(self):
        """
        Disconnect from the IDotMatrix server.
        """
        await self._connection_manager.disconnect()
