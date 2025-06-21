import logging
from typing import Union

from idotmatrix.modules import IDotMatrixModule


class CountdownModule(IDotMatrixModule):
    """This class contains the management of the Countdown of the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def set_mode(
        self, mode: int, minutes: int, seconds: int
    ):
        """Sets the countdown (and activates or disables it)

        Args:
            mode (int): mode of the countdown. 0 = disable, 1 = start, 2 = pause, 3 = restart
            minutes (int): minutes to count down from
            seconds (int): seconds to count down from
        """
        if mode not in range(0, 4):
            raise ValueError("Countdown.setMode expects parameter mode to be between 0 and 3")
        # TODO: check for valid range of minutes
        if seconds > 59 or seconds < 0:
            self.logging.error(
                "Countdown.setMode parameter seconds is not in range between 0 and 59"
            )
            return False
        data = bytearray(
            [
                7,
                0,
                8,
                128,
                mode % 256,
                minutes % 256,
                seconds % 256,
            ]
        )
        await self.send_bytes(data=data)
