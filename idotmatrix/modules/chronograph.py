import logging

from idotmatrix import protocol
from idotmatrix.modules import IDotMatrixModule
from idotmatrix.protocol import build_command


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
        data: bytearray = build_command(protocol.CHRONOGRAPH, mode)
        await self._send_bytes(data=data)
