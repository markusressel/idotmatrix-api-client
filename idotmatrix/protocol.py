from typing import NamedTuple


class Command(NamedTuple):
    """
    A command of the device, identified by its command and subcommand byte (the third and fourth byte of a message).
    See docs/DEVICE-PROTOCOL.md for what is known about them.
    """
    opcode: int
    subcommand: int


# generic
FREEZE_SCREEN = Command(3, 0)  # toggles
RESET = Command(3, 0x80)
SET_SPEED = Command(3, 1)  # not acknowledged
SET_TIME = Command(1, 0x80)
SET_PASSWORD = Command(4, 2)
BRIGHTNESS = Command(4, 0x80)
SCREEN_FLIP = Command(6, 0x80)
SCREEN_ON_OFF = Command(7, 1)
SET_JOINT = Command(12, 0x80)  # not acknowledged
DELETE_MATERIALS = Command(2, 1)

# modes
CLOCK = Command(6, 1)
CLOCK_TIME_INDICATOR = Command(7, 0x80)
FULLSCREEN_COLOR = Command(2, 2)
EFFECT = Command(3, 2)
COUNTDOWN = Command(8, 0x80)
CHRONOGRAPH = Command(9, 0x80)
SCOREBOARD = Command(10, 0x80)
ECO = Command(2, 0x80)
GRAFFITI = Command(5, 1)  # pixels, the length is two bytes
MICROPHONE_MODE = Command(11, 0x80)
IMAGE_RHYTHM = Command(0, 2)  # phone microphone data


def build_command(command: Command, *payload: int, length: int | None = None) -> bytearray:
    """
    Builds a command message: the length of the message (two bytes, little endian), the command and subcommand
    byte and the payload.

    Args:
        command: The command.
        payload: The bytes behind the command, they have to be between 0 and 255.
        length: The length to write into the message, if it differs from the real one (the effect command does that).
    """
    real_length = 4 + len(payload)
    if length is None:
        length = real_length
    return bytearray([length % 256, length // 256, command.opcode, command.subcommand, *payload])
