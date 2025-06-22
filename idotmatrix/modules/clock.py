import logging
from asyncio import sleep
from enum import Enum
from typing import Tuple

from idotmatrix.modules import IDotMatrixModule


class ClockStyle(Enum):
    """Enum for the different clock styles."""

    RGBSwipeOutline = 0
    ChristmasTree = 1
    Checkers = 2
    Color = 3
    Hourglass = 4
    AlarmClock = 5
    Outlines = 6
    RGBCorners = 7


class ClockModule(IDotMatrixModule):
    """This class contains the management of the iDotMatrix clock.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def show(
        self,
        style: ClockStyle | int = ClockStyle.RGBSwipeOutline,
        show_date: bool = True,
        hour24: bool = True,
        color: Tuple[int, int, int] | None = None,
    ):
        """Set the clock mode of the device.

        Args:
            style (int): Style of the clock.
            show_date (bool): Whether the date should be shown or not. Defaults to True.
            hour24 (bool): 12 or 24 hour format. Defaults to True.
            color (tuple, optional): Color of the clock in RGB format. Defaults to (255, 255, 255).
        """
        if isinstance(style, ClockStyle):
            style = style.value

        if style not in range(0, 8):
            raise ValueError("style must be one of the ClockStyle enum values or an integer between 0 and 7")

        r, g, b = (255, 255, 255)
        if isinstance(color, tuple) and len(color) == 3:
            if not all(isinstance(c, int) for c in color):
                raise ValueError("color must be a tuple of three integers (r, g, b)")
            if not all(0 <= c < 256 for c in color):
                raise ValueError("color values must be between 0 and 255")

            r, g, b = color

        data = self._create_payload(
            style=style,
            show_date=show_date,
            hour24=hour24,
            r=r, g=g, b=b
        )
        await self.send_bytes(data=data)
        await sleep(0.1)

    async def set_time_indicator(self, enabled: bool = True):
        """
        Sets the time indicator of the clock. Does not seem to work currently (maybe in a future update?).
        It is inside the source code of BleProtocolN.java, but not referenced anywhere.

        Args:
            enabled (bool, optional): Whether to show the time indicator of the clock. Defaults to True.
        """
        data: bytearray = bytearray(
            [
                5,
                0,
                7,
                128,
                1 if enabled else 0,
            ]
        )
        await self.send_bytes(data=data)

    @staticmethod
    def _create_payload(
        style: int,
        show_date: bool,
        hour24: bool,
        r: int, g: int, b: int
    ) -> bytearray:
        """Create a payload for the clock settings.

        Args:
            style (int): Style of the clock.
            show_date (bool): Whether the date should be shown or not.
            hour24 (bool): 12 or 24 hour format.
            r (int): Color red.
            g (int): Color green.
            b (int): Color blue.
        """
        data: bytearray = bytearray(
            [
                8,
                0,
                6,
                1,
                (style | (128 if show_date else 0)) | (64 if hour24 else 0),
                r % 256,
                g % 256,
                b % 256,
            ]
        )
        return data
