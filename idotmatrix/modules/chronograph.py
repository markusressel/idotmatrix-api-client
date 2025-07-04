import logging

from idotmatrix.modules import IDotMatrixModule


class ChronographModule(IDotMatrixModule):
    """
    This class contains the Chronograph controls for the iDotMatrix device.
    """
    logging = logging.getLogger(__name__)

    async def reset(self):
        """
        Resets the Chronograph to zero.
        Also shows the Chronograph on the screen, if it was not already visible.
        """
        await self._set_mode(0)

    async def start_from_zero(self):
        """
        Starts the Chronograph from zero.
        Also shows the Chronograph on the screen, if it was not already visible.
        """
        await self._set_mode(1)

    async def pause(self):
        """
        Pauses the Chronograph.
        """
        await self._set_mode(2)

    async def resume(self):
        """
        Resumes the Chronograph after it was paused.
        """
        await self._set_mode(3)

    async def _set_mode(self, mode: int):
        """
        Starts/Stops the Chronograph.

        Args:
            mode (int): 0 = reset, 1 = (re)start, 2 = pause, 3 = continue after pause
        """
        if mode not in range(0, 4):
            raise ValueError("Chronograph.setMode expects parameter mode to be between 0 and 3")
        data: bytearray = bytearray(
            [
                5,
                0,
                9,
                128,
                mode,
            ]
        )
        await self._send_bytes(data=data)
