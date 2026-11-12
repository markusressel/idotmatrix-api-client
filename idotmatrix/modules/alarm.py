import asyncio
import binascii
import logging
from collections.abc import Callable, Iterable
from datetime import datetime
from enum import IntEnum
from os import PathLike
from typing import Tuple

from idotmatrix import protocol
from idotmatrix.connection_manager import ConnectionManager
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.modules.common import CommonModule
from idotmatrix.modules.gif import CHUNK_SIZE_4096, GifModule
from idotmatrix.protocol import build_command
from idotmatrix.util import color_utils
from idotmatrix.util.image_utils import ResizeMode

# The alarms the official app offers (0 to 9, according to issue #51). Only slot 0 was seen to ring, on a 16x16
# (docs/DEVICE-PROTOCOL.md).
ALARM_SLOTS = tuple(range(10))
# The ring durations the official app offers, in seconds. The header has two bytes for it.
APP_RING_DURATIONS_SECONDS = (10, 30, 60, 300, 900)
DEFAULT_RING_DURATION_SECONDS = 10
MAX_RING_DURATION_SECONDS = 0xFFFF

HEADER_SIZE_ALARM = 24
# the type of the picture the alarm shows (byte 10 of the header): 1 = GIF, 2 = raw 16x16 RGB, 3 = text
PICTURE_TYPE_GIF = 1
# the official app gives the picture of an alarm the id slot + 20 (the last byte of the header)
PICTURE_ID_OFFSET = 20


class Weekday(IntEnum):
    """The days an alarm repeats on, numbered like `datetime.weekday()`."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class AlarmModule(IDotMatrixModule):
    """
    The alarms of the device. When an alarm goes off the device shows its picture and, if the buzzer is on, beeps.
    This is the only known way to make the device beep: there is no command that just beeps.

    Based on `TimerAgreement.sendData` of the official Android app (2.1.7), as described by a third party who
    confirmed the bytes with a capture of the app and made a 16x16 beep with them (issue #51). Not tested by us yet,
    see docs/DEVICE-PROTOCOL.md.

    The device keeps the time only while it is powered, and an alarm only goes off at the real time: set the time
    (the default of `set_alarm`) and then the alarm for a later minute.
    """

    logging = logging.getLogger(__name__)

    def __init__(self, connection_manager: ConnectionManager, gif: GifModule, common: CommonModule) -> None:
        super().__init__(connection_manager=connection_manager)
        self._gif = gif
        self._common = common

    async def set_alarm(
        self,
        slot: int,
        hour: int,
        minute: int,
        file_path: PathLike | str,
        weekdays: Iterable[Weekday | int] | None = None,
        ring_duration: int = DEFAULT_RING_DURATION_SECONDS,
        buzzer: bool = True,
        sync_time: bool = True,
        resize_mode: ResizeMode = ResizeMode.FIT,
        background_color: Tuple[int, int, int] | int | str = (0, 0, 0),
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        """
        Sets an alarm. The device shows its picture right away as a preview (replacing what is on screen), and again
        when the alarm goes off.

        Args:
            slot (int): The alarm to set (0 to 9). Only slot 0 is known to ring, slot 9 did not on a 16x16.
            hour (int): The hour the alarm goes off (0 to 23).
            minute (int): The minute the alarm goes off (0 to 59).
            file_path (PathLike | str): The picture shown while the alarm rings, a GIF or any other picture. It is
                converted like for `GifModule.upload_gif_file`.
            weekdays (Iterable[Weekday | int], optional): The days the alarm repeats on (0 = Monday to 6 = Sunday).
                The alarm goes off once if none are given.
            ring_duration (int): How long the alarm rings, in seconds (1 to 65535). The official app offers 10, 30,
                60, 300 and 900.
            buzzer (bool): Whether the device beeps while the alarm rings. Defaults to True.
            sync_time (bool): Whether to set the time of the device to the current time first. An alarm only goes off
                if the device knows the time, which it loses when it is powered off. Defaults to True.
            resize_mode (ResizeMode): How the picture is fitted to the screen.
            background_color (Tuple[int, int, int] | int | str): The color of transparent pixels. Defaults to black.
            progress (Callable[[int, int], None], optional): Called with (chunks sent, chunks in total) while the
                picture is transferred, see `ConnectionManager.send_packets`.

        Raises:
            UploadError: If the device does not acknowledge a part in time. Only the acknowledgement that accepts a
                part is known, so a rejection shows up as a missing acknowledgement.

        For a while after an alarm went off the device keeps showing its picture and ignores new uploads (about
        3 minutes on a 16x16).
        """
        flags = self._flags(enabled=True, weekdays=weekdays)
        self._validate(slot=slot, hour=hour, minute=minute, ring_duration=ring_duration)
        background_color = color_utils.parse_color_rgb(background_color)

        # reading and converting the file takes a while, the event loop must not be blocked
        gif_data = await asyncio.to_thread(
            self._gif._load_gif_and_adapt_to_canvas,
            file_path=file_path,
            canvas_size=self._gif.screen_size.value[0],
            resize_mode=resize_mode,
            background_color=background_color,
        )

        if sync_time:
            await self._common.set_time(datetime.now())

        packets = self._create_alarm_packets(
            gif_data=gif_data, slot=slot, flags=flags, hour=hour, minute=minute,
            ring_duration=ring_duration, buzzer=buzzer,
        )
        await self._send_packets(packets=packets, response=True, wait_for_ack=True, progress=progress)

    async def disable_alarm(
        self,
        slot: int,
        hour: int,
        minute: int,
        weekdays: Iterable[Weekday | int] | None = None,
        ring_duration: int = DEFAULT_RING_DURATION_SECONDS,
        buzzer: bool = True,
    ) -> None:
        """
        Switches an alarm off. The official app sends the settings of the alarm with the "enabled" bit cleared and
        without a picture. Whether the device needs the settings of the alarm or only its slot is not known, so pass
        the ones it was set with to be safe. Untested.

        Args:
            slot (int): The alarm to switch off (0 to 9).
            hour (int): The hour of the alarm (0 to 23).
            minute (int): The minute of the alarm (0 to 59).
            weekdays (Iterable[Weekday | int], optional): The days the alarm repeats on (0 = Monday to 6 = Sunday).
            ring_duration (int): How long the alarm rings, in seconds (1 to 65535).
            buzzer (bool): Whether the alarm beeps.
        """
        flags = self._flags(enabled=False, weekdays=weekdays)
        self._validate(slot=slot, hour=hour, minute=minute, ring_duration=ring_duration)
        data = build_command(
            protocol.ALARM, slot, flags, hour, minute, *ring_duration.to_bytes(2, byteorder="little"),
            PICTURE_TYPE_GIF, 1 if buzzer else 0,
        )
        await self._send_bytes(data=data)

    @staticmethod
    def _create_alarm_packets(
        gif_data: bytes,
        slot: int,
        flags: int,
        hour: int,
        minute: int,
        ring_duration: int,
        buzzer: bool,
    ) -> list[list[bytearray]]:
        """
        Creates the packets of an alarm with a GIF: the picture split into parts of 4096 bytes, each with a header
        of 24 bytes in front (`TimerAgreement.sendData`). The header has the length of the packet, the command
        (`00 80`), the settings of the alarm, whether it is the first part, the size and CRC-32 of the whole picture
        and the id of the picture.

        Returns:
            One packet per part, each a list of BLE packets.
        """
        if not gif_data:
            raise ValueError("gif_data cannot be empty")

        total_length = len(gif_data).to_bytes(4, byteorder="little")
        crc32 = (binascii.crc32(gif_data) & 0xFFFFFFFF).to_bytes(4, byteorder="little")

        packets = []
        for offset in range(0, len(gif_data), CHUNK_SIZE_4096):
            part = gif_data[offset:offset + CHUNK_SIZE_4096]
            header = bytearray(HEADER_SIZE_ALARM)
            header[0:2] = (HEADER_SIZE_ALARM + len(part)).to_bytes(2, byteorder="little")
            header[2] = protocol.ALARM.opcode
            header[3] = protocol.ALARM.subcommand
            header[4] = slot
            header[5] = flags
            header[6] = hour
            header[7] = minute
            header[8:10] = ring_duration.to_bytes(2, byteorder="little")
            header[10] = PICTURE_TYPE_GIF
            header[11] = 1 if buzzer else 0
            header[12] = 2 if offset else 0  # 0 for the first part, 2 for the following ones
            header[13:17] = total_length
            header[17:21] = crc32
            # bytes 21 and 22 stay 0
            header[23] = slot + PICTURE_ID_OFFSET
            packets.append(GifModule._create_ble_packets(bytes(header) + part))
        return packets

    @staticmethod
    def _flags(enabled: bool, weekdays: Iterable[Weekday | int] | None) -> int:
        """Bit 0: the alarm is on, bits 1 to 7: the days it repeats on (Monday to Sunday), none for once."""
        flags = 1 if enabled else 0
        for day in weekdays or ():
            if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 6:
                raise ValueError(f"weekdays must be between 0 (Monday) and 6 (Sunday), got: {day!r}")
            flags |= 1 << (day + 1)
        return flags

    @staticmethod
    def _validate(slot: int, hour: int, minute: int, ring_duration: int) -> None:
        for name, value, valid in (
            ("slot", slot, range(len(ALARM_SLOTS))),
            ("hour", hour, range(24)),
            ("minute", minute, range(60)),
            ("ring_duration", ring_duration, range(1, MAX_RING_DURATION_SECONDS + 1)),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value not in valid:
                raise ValueError(f"{name} must be between {valid[0]} and {valid[-1]}, got: {value!r}")
