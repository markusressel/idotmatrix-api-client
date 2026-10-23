from dataclasses import dataclass
from typing import Optional

from idotmatrix import protocol
from idotmatrix.screensize import ScreenSize

# the screen type the device reports, 2 (8x32) and 11 (16x64) exist, but are not supported by this library
SCREEN_TYPES = {
    1: ScreenSize.SIZE_16x16,
    3: ScreenSize.SIZE_32x32,
    4: ScreenSize.SIZE_64x64,
}


@dataclass(frozen=True)
class DeviceInfo:
    """What the device tells about itself when its time is set (`09 00 01 80 <major> <minor> <?> <type> <password>`)."""
    firmware_version: str
    screen_type: int
    password_protected: bool
    switch_status: int

    @property
    def screen_size(self) -> Optional[ScreenSize]:
        """The size of the screen, or None if the type is not supported by this library."""
        return SCREEN_TYPES.get(self.screen_type)


def parse_device_info(notification: bytes) -> Optional[DeviceInfo]:
    """Parses the reply to the set time command. Returns None for any other notification."""
    if len(notification) < 9 or (notification[2], notification[3]) != (protocol.SET_TIME.opcode, protocol.SET_TIME.subcommand):
        return None
    return DeviceInfo(
        firmware_version=f"{notification[4]}.{notification[5]:02d}",
        switch_status=notification[6],
        screen_type=notification[7],
        password_protected=notification[8] == 1,
    )
