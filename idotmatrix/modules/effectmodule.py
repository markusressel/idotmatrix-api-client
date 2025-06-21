import logging
from typing import Union

from idotmatrix.modules import IDotMatrixModule

"""
The effect modes are:
0 graduated horizontal rainbow
1 random coloured pixels on black
2 random white pixels on changing background
3 vertical rainbow
4 diagonal right rainbow
5 diagonal left rainbow, on black background
6 random coloured pixels
"""


class EffectModule(IDotMatrixModule):
    """This class contains the Effect controls for the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def set_mode(
        self,
        style: int,
        rgb_values: list[tuple[int, int, int]],
    ):
        """Set the effect mode of the device.

        Args:
            style (int): Style of the effect 0-6.
            rgb_values (list[tuple[int, int, int]]): list of red, green, blue tuples 2-7.
        """
        if style not in range(0, 7):
            raise ValueError("effect.setMode expects parameter style to be between 0 and 6")

        if len(rgb_values) not in range(2, 8):
            raise ValueError("effect.setMode expects parameter rgb_values to be a list of tuples to be between 2 and 7")

        for rgb in rgb_values:
            for r, g, b in [rgb]:
                if r not in range(0, 256) or g not in range(0, 256) or b not in range(0, 256):
                    raise ValueError("effect.setMode expects parameter rgb_values to be a list of tuples of red, green, blue values between 0 and 255")

        processed_rgb_values = [
            (r % 256, g % 256, b % 256)
            for rgb in rgb_values
            for r, g, b in [rgb + (255,) * (3 - len(rgb))]
        ]

        data = bytearray(
            [
                6 + len(processed_rgb_values),
                0,
                3,
                2,
                style % 256,
                90,
                len(processed_rgb_values) % 256,
            ] + [component for rgb in processed_rgb_values for component in rgb]
        )

        await self.send_bytes(data=data)
