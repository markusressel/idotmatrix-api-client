# Index (the last byte of the header) of an upload to the device. 0 to 11 are slots the device keeps
# and cycles through, 13 is the one the official app uses to show something on the device right away.
INDEX_SHOW_NOW = 13

# The slots (0 to 11, verified on a 64x64: items stay stored, are cycled through in the order of the slots, and an upload
# of the same data again is skipped by the device) that can hold items.
SLOTS = tuple(range(12))
DEFAULT_DISPLAY_TIME_SECONDS = 5
MAX_DISPLAY_TIME_SECONDS = 0xFFFF


def validate_slot(slot: int) -> int:
    """Raises a ValueError for a slot the device does not have."""
    if isinstance(slot, bool) or not isinstance(slot, int) or slot not in SLOTS:
        raise ValueError(f"slot must be one of 0 to {SLOTS[-1]}, got: {slot!r}")
    return slot


def validate_display_time(seconds: int) -> int:
    """Raises a ValueError for a display time that does not fit the two bytes of the header."""
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= MAX_DISPLAY_TIME_SECONDS:
        raise ValueError(f"display_time must be between 1 and {MAX_DISPLAY_TIME_SECONDS} seconds, got: {seconds!r}")
    return seconds


def convert_display_time(time_sign: int) -> int:
    """
    Python equivalent of DeviceMaterialTimeConvert.ConvertTime(int i).
    The time sign corresponds to AppData.getInstance().getTimeSign() of the official app, which is the
    display time of an item in the list of stored materials of the device. It originates from
    SharedPreferences, and 0 is the default.

    Returns:
        The display time in seconds.
    """
    return {1: 10, 2: 30, 3: 60, 4: 300}.get(time_sign, 5)
