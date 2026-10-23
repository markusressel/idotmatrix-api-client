from idotmatrix import protocol

# Commands (identified by their command and subcommand byte, the third and fourth byte) that the device
# acknowledges with `05 00 <command> <subcommand> <status>`, verified on a 64x64. See docs/DEVICE-PROTOCOL.md,
# and add a command here once it was verified. Commands that are not in here are never waited for:
# `set_speed` and `set_joint` are not acknowledged, freeze, text and set_time are answered differently.
ACKNOWLEDGED_COMMANDS = frozenset({
    protocol.BRIGHTNESS,
    protocol.SCREEN_FLIP,
    protocol.SCREEN_ON_OFF,
    protocol.CLOCK,
    protocol.FULLSCREEN_COLOR,
    protocol.EFFECT,
    protocol.COUNTDOWN,
    protocol.CHRONOGRAPH,
    protocol.SCOREBOARD,
    protocol.MICROPHONE_MODE,
    protocol.DELETE_MATERIALS,
})


def is_acknowledged_command(data: bytes | bytearray) -> bool:
    """Tells if the device is known to acknowledge a command."""
    return len(data) >= 5 and protocol.Command(data[2], data[3]) in ACKNOWLEDGED_COMMANDS
