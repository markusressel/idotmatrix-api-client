# Commands (identified by their command and subcommand byte, the third and fourth byte) that the device
# acknowledges with `05 00 <command> <subcommand> <status>`, verified on a 64x64. See docs/DEVICE-PROTOCOL.md,
# and add a command here once it was verified. Commands that are not in here are never waited for:
# `set_speed` and `set_joint` are not acknowledged, freeze, text and set_time are answered differently.
ACKNOWLEDGED_COMMANDS = frozenset({
    (4, 0x80),  # brightness
    (6, 0x80),  # flip
    (7, 1),  # screen on / off
    (6, 1),  # clock
    (2, 2),  # fullscreen color
    (3, 2),  # effect
    (8, 0x80),  # countdown
    (9, 0x80),  # chronograph
    (0x0a, 0x80),  # scoreboard
    (0x0b, 0x80),  # microphone mode
})


def is_acknowledged_command(data: bytes | bytearray) -> bool:
    """Tells if the device is known to acknowledge a command."""
    return len(data) >= 5 and (data[2], data[3]) in ACKNOWLEDGED_COMMANDS
