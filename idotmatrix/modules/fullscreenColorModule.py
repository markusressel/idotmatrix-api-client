import logging
from typing import Union

from idotmatrix.modules import IDotMatrixModule


class FullscreenColorModule(IDotMatrixModule):
    """This class contains the management of the iDotMatrix fullscreen color mode.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def set_mode(
        self, r: int = 0, g: int = 0, b: int = 0
    ):
        """Sets the fullscreen color of the screen of the device

        Args:
            r (int, optional): color red. Defaults to 0.
            g (int, optional): color green. Defaults to 0.
            b (int, optional): color blue. Defaults to 0.
        """
        if r not in range(0, 256):
            raise ValueError("FullscreenColor.setMode expects parameter r to be between 0 and 255")
        if g not in range(0, 256):
            raise ValueError("FullscreenColor.setMode expects parameter g to be between 0 and 255")
        if b not in range(0, 256):
            raise ValueError("FullscreenColor.setMode expects parameter b to be between 0 and 255")

        data = bytearray(
            [
                7,
                0,
                2,
                2,
                int(r) % 256,
                int(g) % 256,
                int(b) % 256,
            ]
        )
        await self.send_bytes(data=data)
