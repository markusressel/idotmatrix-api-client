import logging
from typing import Union

from idotmatrix.modules import IDotMatrixModule


class ClockModule(IDotMatrixModule):
    """This class contains the management of the iDotMatrix clock.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def set_time_indicator(self, enabled: bool = True):
        """Sets the time indicator of the clock. Does not seem to work currently (maybe in a future update?).
        It is inside the source code of BleProtocolN.java, but not referenced anywhere.

        Args:
            enabled (bool, optional): Whether or not to show the time indicator of the clock. Defaults to True.

        Returns:
            Union[bool, bytearray]: False if input validation fails, otherwise byte array of the command which needs to be sent to the device.
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

    async def set_mode(
        self,
        style: int,
        show_date: bool = True,
        hour24: bool = True,
        r: int = 255,
        g: int = 255,
        b: int = 255,
    ):
        """Set the clock mode of the device.

        Args:
            style (int): Style of the clock.
            show_date (bool): Whether the date should be shown or not. Defaults to True.
            hour24 (bool): 12 or 24 hour format. Defaults to True.
            r (int, optional): Color red. Defaults to 255.
            g (int, optional): Color green. Defaults to 255.
            b (int, optional): Color blue. Defaults to 255.

        Returns:
            Union[bool, bytearray]: False if input validation fails, otherwise byte array of the command which needs to be sent to the device.
        """
        if style not in range(0, 8):
            self.logging.error(
                "Clock.setMode expects parameter style to be between 0 and 7"
            )
            return False
        if r not in range(0, 256):
            self.logging.error(
                "Clock.setMode expects parameter r to be between 0 and 255"
            )
            return False
        if g not in range(0, 256):
            self.logging.error(
                "Clock.setMode expects parameter g to be between 0 and 255"
            )
            return False
        if b not in range(0, 256):
            self.logging.error(
                "Clock.setMode expects parameter b to be between 0 and 255"
            )
            return False
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
        await self.send_bytes(data=data)
