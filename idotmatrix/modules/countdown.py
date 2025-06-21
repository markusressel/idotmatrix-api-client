import logging

from idotmatrix.modules import IDotMatrixModule


class CountdownModule(IDotMatrixModule):
    """This class contains the management of the Countdown of the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def set_mode(
        self, mode: int, minutes: int, seconds: int
    ):
        """
        Sets the countdown (and activates or disables it)

        Args:
            mode (int): mode of the countdown. 0 = disable, 1 = start, 2 = pause, 3 = restart
            minutes (int): minutes to count down from
            seconds (int): seconds to count down from
        """
        if mode not in range(0, 4):
            raise ValueError("Countdown.setMode expects parameter mode to be between 0 and 3")
        # TODO: check for valid range of minutes
        if seconds > 59 or seconds < 0:
            raise ValueError("Countdown.setMode expects parameter seconds to be between 0 and 59")
        if minutes > 59 or minutes < 0:
            raise ValueError("Countdown.setMode expects parameter minutes to be between 0 and 59")

        data = self._create_payload(
            mode=mode,
            minutes=minutes,
            seconds=seconds,
        )
        await self.send_bytes(data=data)

    @staticmethod
    def _create_payload(mode, minutes, seconds) -> bytearray:
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
        return data
