import logging
from typing import Union

from idotmatrix.modules import IDotMatrixModule


class GraffitiModule(IDotMatrixModule):
    """This class contains the Graffiti controls for the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def set_pixel(
        self, r: int, g: int, b: int, x: int, y: int
    ):
        """Set the scoreboard of the device.

        Args:
            r (int): color red value
            g (int): color green value
            b (int): color blue value
            x (int): pixel x position
            y (int): pixel y position

        Returns:
            Union[bool, bytearray]: False if there's an error, otherwise byte array of the command which needs to be sent to the device.
        """
        if r not in range(0, 256):
            raise ValueError("Graffiti.setPixel expects parameter r to be between 0 and 255")
        if g not in range(0, 256):
            raise ValueError("Graffiti.setPixel expects parameter g to be between 0 and 255")
        if b not in range(0, 256):
            raise ValueError("Graffiti.setPixel expects parameter b to be between 0 and 255")

        if x not in range(0, 256):
            raise ValueError("Graffiti.setPixel expects parameter x to be between 0 and 255")
        if y not in range(0, 256):
            raise ValueError("Graffiti.setPixel expects parameter y to be between 0 and 255")

        data = bytearray(
            [
                10,
                0,
                5,
                1,
                0,
                r % 256,  # Ensure R, G, B, X, Y are within byte range
                g % 256,
                b % 256,
                x % 256,
                y % 256,
            ]
        )
        await self.send_bytes(data=data)
