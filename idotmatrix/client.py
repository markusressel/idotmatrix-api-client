from typing import Optional

from idotmatrix.connectionManager import ConnectionManager
from idotmatrix.modules.chronographmodule import ChronographModule
from idotmatrix.modules.clockmodule import ClockModule
from idotmatrix.modules.commonmodule import CommonModule
from idotmatrix.modules.countdownmodule import CountdownModule
from idotmatrix.modules.ecomodule import EcoModule
from idotmatrix.modules.effectmodule import EffectModule
from idotmatrix.modules.fullscreenColorModule import FullscreenColorModule
from idotmatrix.modules.gifmodule import GifModule
from idotmatrix.modules.graffitimodule import GraffitiModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.modules.musicSyncModule import MusicSyncModule
from idotmatrix.modules.scoreboardmodule import ScoreboardModule
from idotmatrix.modules.systemmodule import SystemModule
from idotmatrix.modules.textmodule import TextModule
from idotmatrix.screensize import ScreenSize


class IDotMatrixClient:

    def __init__(
        self,
        screen_size: ScreenSize,
        mac_address: Optional[str] = None,
    ):
        self._connection_manager = ConnectionManager()
        self._connection_manager.address = mac_address
        self.screen_size = screen_size
        self.mac_address = mac_address

    @property
    def chronograph(self) -> ChronographModule:
        return ChronographModule(
            connection_manager=self._connection_manager,
        )

    @property
    def clock(self) -> ClockModule:
        return ClockModule(
            connection_manager=self._connection_manager,
        )

    @property
    def common(self) -> CommonModule:
        return CommonModule(
            connection_manager=self._connection_manager,
        )

    @property
    def countdown(self) -> CountdownModule:
        return CountdownModule(
            connection_manager=self._connection_manager,
        )

    @property
    def eco(self) -> EcoModule:
        return EcoModule(
            connection_manager=self._connection_manager,
        )

    @property
    def effect(self) -> EffectModule:
        return EffectModule(
            connection_manager=self._connection_manager,
        )

    @property
    def color(self) -> FullscreenColorModule:
        return FullscreenColorModule(
            connection_manager=self._connection_manager,
        )

    @property
    def gif(self) -> GifModule:
        return GifModule(
            connection_manager=self._connection_manager,
            screen_size=self.screen_size
        )

    @property
    def graffiti(self) -> GraffitiModule:
        return GraffitiModule(
            connection_manager=self._connection_manager,
        )

    @property
    def image(self) -> ImageModule:
        return ImageModule(
            connection_manager=self._connection_manager,
            screen_size=self.screen_size
        )

    @property
    def music_sync(self) -> MusicSyncModule:
        return MusicSyncModule(
            connection_manager=self._connection_manager,
        )

    @property
    def scoreboard(self) -> ScoreboardModule:
        return ScoreboardModule(
            connection_manager=self._connection_manager,
        )

    @property
    def system(self) -> SystemModule:
        return SystemModule(
            connection_manager=self._connection_manager,
        )

    @property
    def text(self) -> TextModule:
        return TextModule(
            connection_manager=self._connection_manager,
        )

    async def connect(self):
        """
        Connect to the IDotMatrix server.
        """
        if self.mac_address:
            await self._connection_manager.connect_by_address(self.mac_address)
        else:
            await self._connection_manager.connect_by_discovery()

    async def disconnect(self):
        """
        Disconnect from the IDotMatrix server.
        """
        await self._connection_manager.disconnect()
