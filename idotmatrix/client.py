from collections.abc import Callable
from functools import cached_property
from typing import Optional

from bleak.backends.device import BLEDevice

from idotmatrix.connection_manager import ConnectionManager, ConnectionListener
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
from idotmatrix.modules.materials import MaterialsModule
from idotmatrix.modules.music_sync import MusicSyncModule
from idotmatrix.modules.scoreboard import ScoreboardModule
from idotmatrix.modules.system import SystemModule
from idotmatrix.modules.text import TextModule
from idotmatrix.screensize import ScreenSize
from idotmatrix.transport import Transport


class IDotMatrixClient:
    """
    Client for interacting with the iDotMatrix device.
    """

    def __init__(
        self,
        screen_size: Optional[ScreenSize] = None,
        mac_address: Optional[str] = None,
        max_ble_packet_size: Optional[int] = None,
        ble_device: Optional[BLEDevice] = None,
        transport_factory: Optional[Callable[[str | BLEDevice, Callable[[], None]], Transport]] = None,
        install_signal_handlers: bool = True,
    ):
        """
        Initializes the IDotMatrix client with the specified screen size and optional MAC address.

        Args:
            screen_size (Optional[ScreenSize]): The size of the screen, e.g., ScreenSize.SIZE_64x64. If not provided,
                                                it is asked from the device when connecting (see `detect_screen_size`).
            mac_address (Optional[str]): The Bluetooth MAC address of the iDotMatrix device. If not provided,
                                         the client will attempt to discover devices.
            max_ble_packet_size (Optional[int]): Overrides the detected maximum size of a single BLE write.
                                                 Only needed if the BLE stack misreports the negotiated MTU.
            ble_device (Optional[BLEDevice]): The device to connect to, as found by a scanner. Instead of `mac_address`,
                                              f.e. for the scanner of Home Assistant. See `ConnectionManager.set_device`.
            transport_factory (Optional[Callable]): Creates the `Transport` that talks to the device, to connect in a
                                                    different way than `bleak` does by default. See `ConnectionManager`.
            install_signal_handlers (bool): Whether to close the connection on SIGINT and SIGTERM. Turn it off if the
                                            application handles these signals itself (f.e. Home Assistant).
        """
        self._connection_manager = ConnectionManager(
            address=mac_address,
            max_ble_packet_size=max_ble_packet_size,
            transport_factory=transport_factory,
            install_signal_handlers=install_signal_handlers,
        )
        self._uses_ble_device = ble_device is not None
        if ble_device is not None:
            mac_address = ble_device.address
            self._connection_manager.set_device(ble_device)
        self._screen_size = screen_size
        self.mac_address = mac_address

    @property
    def screen_size(self) -> ScreenSize:
        """
        The size of the screen. If it was not given, it is only known after `connect` or `detect_screen_size`.

        Raises:
            RuntimeError: If the size is not known yet.
        """
        if self._screen_size is None:
            raise RuntimeError(
                "The screen size is not known yet, pass screen_size to IDotMatrixClient, or connect first to let "
                "the client ask the device.")
        return self._screen_size

    @property
    def screen_size_known(self) -> bool:
        """Whether the size of the screen is known, f.e. because it was given or detected."""
        return self._screen_size is not None

    @screen_size.setter
    def screen_size(self, screen_size: ScreenSize) -> None:
        self._screen_size = screen_size

    @cached_property
    def chronograph(self) -> ChronographModule:
        return ChronographModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def clock(self) -> ClockModule:
        return ClockModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def common(self) -> CommonModule:
        return CommonModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def countdown(self) -> CountdownModule:
        return CountdownModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def eco(self) -> EcoModule:
        return EcoModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def effect(self) -> EffectModule:
        return EffectModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def color(self) -> FullscreenColorModule:
        return FullscreenColorModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def gif(self) -> GifModule:
        return GifModule(
            connection_manager=self._connection_manager,
            screen_size=self.screen_size
        )

    @cached_property
    def graffiti(self) -> GraffitiModule:
        return GraffitiModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def image(self) -> ImageModule:
        return ImageModule(
            connection_manager=self._connection_manager,
            screen_size=self.screen_size
        )

    @cached_property
    def materials(self) -> MaterialsModule:
        return MaterialsModule(
            connection_manager=self._connection_manager,
            gif=self.gif,
            image=self.image,
        )

    @cached_property
    def music_sync(self) -> MusicSyncModule:
        return MusicSyncModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def scoreboard(self) -> ScoreboardModule:
        return ScoreboardModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def system(self) -> SystemModule:
        return SystemModule(
            connection_manager=self._connection_manager,
        )

    @cached_property
    def text(self) -> TextModule:
        return TextModule(
            connection_manager=self._connection_manager,
        )

    async def connect(self):
        """
        Connect to the IDotMatrix device.
        """
        if self._uses_ble_device:
            # connecting by address would replace the BLEDevice
            await self._connection_manager.connect()
        elif self.mac_address:
            await self._connection_manager.connect_by_address(self.mac_address)
        else:
            await self._connection_manager.connect_by_discovery()

        if self._screen_size is None:
            await self.detect_screen_size()

    async def detect_screen_size(self) -> ScreenSize:
        """
        Asks the device for the size of its screen and uses it from now on. This also sets the time of the device,
        see `CommonModule.get_device_info`.

        Returns:
            ScreenSize: The size of the screen.
        Raises:
            RuntimeError: If the device does not answer, or has a screen that this library does not support.
        """
        info = await self.common.get_device_info()
        if info is None:
            raise RuntimeError("The device did not tell the size of its screen, pass screen_size to IDotMatrixClient.")
        if info.screen_size is None:
            raise RuntimeError(
                f"The screen type {info.screen_type} of the device is not supported, firmware {info.firmware_version}.")
        self._screen_size = info.screen_size
        return info.screen_size

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """
        Hands over a newer `BLEDevice` of the device, f.e. when the scanner of Home Assistant found it again. An
        established connection is not interrupted, the new one is used for the next connection.
        """
        self._uses_ble_device = True
        self.mac_address = ble_device.address
        self._connection_manager.set_device(ble_device)

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

    def add_connection_listener(
        self,
        connection_listener: ConnectionListener,
    ):
        """
        Add listeners for connection events.

        Args:
            connection_listener (ConnectionListener): The listener to be added.
        """
        self._connection_manager.add_connection_listener(connection_listener)

    def set_auto_reconnect(self, auto_reconnect: bool):
        """
        Set whether the client should automatically reconnect to the device if the connection is lost.
        Args:
            auto_reconnect (bool): True to enable auto-reconnect, False to disable.
        """
        self._connection_manager.set_auto_reconnect(auto_reconnect=auto_reconnect)

    def set_heartbeat(self, interval_seconds: Optional[float]):
        """
        Set whether a connection that died silently (f.e. because the device was switched off) is detected.
        While the device is silent for the given time it is asked for a sign of life, and if it does not answer the
        connection is closed, the connection listeners are informed, and the connection is restored if
        `set_auto_reconnect` is enabled.
        Args:
            interval_seconds (Optional[float]): How long the device may be silent before it is checked, or None to disable.
        """
        self._connection_manager.set_heartbeat(interval_seconds=interval_seconds)
