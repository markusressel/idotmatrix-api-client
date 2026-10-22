# Index (the last byte of the header) of an upload to the device. 0 to 11 are slots the device keeps
# and cycles through, 13 is the one the official app uses to show something on the device right away.
INDEX_SHOW_NOW = 13


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
