from typing import Optional

from idotmatrix.connectionManager import ConnectionManager
from idotmatrix.modules.chronograph import ChronographModule
from idotmatrix.modules.clock import ClockModule
from idotmatrix.modules.common import CommonModule
from idotmatrix.modules.countdown import CountdownModule
from idotmatrix.modules.eco import EcoModule
from idotmatrix.modules.effect import EffectModule
from idotmatrix.modules.fullscreen_color import FullscreenColorModule
from idotmatrix.modules.gif import GifModule
from idotmatrix.modules.graffiti import GraffitiModule
from idotmatrix.modules.image import ImageModule
from idotmatrix.modules.music_sync import MusicSyncModule
from idotmatrix.modules.scoreboard import ScoreboardModule
from idotmatrix.modules.system import SystemModule
from idotmatrix.modules.text import TextModule
from idotmatrix.screensize import ScreenSize


class IDotMatrixClient:
    """
    Client for interacting with the iDotMatrix device.
    """

    def __init__(
        self,
        screen_size: ScreenSize,
        mac_address: Optional[str] = None,
    ):
        """
        Initializes the IDotMatrix client with the specified screen size and optional MAC address.

        Args:
            screen_size (ScreenSize): The size of the screen, e.g., ScreenSize.SIZE_64x64.
            mac_address (Optional[str]): The Bluetooth MAC address of the iDotMatrix device. If not provided,
                                         the client will attempt to discover devices.
        """
        self._connection_manager = ConnectionManager(
            address=mac_address,
        )
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
        Connect to the IDotMatrix device.
        """
        if self.mac_address:
            await self._connection_manager.connect_by_address(self.mac_address)
        else:
            await self._connection_manager.connect_by_discovery()

    async def disconnect(self):
        """
        Disconnect from the IDotMatrix device.
        """
        await self._connection_manager.disconnect()

    async def turn_on(self):
        """
        Turn on the IDotMatrix device.
        """
        await self.common.turn_on()

    async def turn_off(self):
        """
        Turn off the IDotMatrix device.
        """
        await self.common.turn_off()

    async def set_brightness(self, brightness_percent: int):
        """
        Set the brightness of the IDotMatrix device.

        Args:
            brightness_percent (int): Brightness level (5-100).
        """
        await self.common.set_brightness(brightness_percent=brightness_percent)

    async def reset(self):
        """
        Reset the IDotMatrix device.
        """
        await self.common.reset()