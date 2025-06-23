import logging
from enum import Enum
from typing import List, Tuple

from idotmatrix.modules import IDotMatrixModule
from idotmatrix.util import color_utils


class EffectStyle(Enum):
    """Enum for the different effect styles."""

    GRADIENT_HORIZONTAL_RAINBOW = 0
    RANDOM_COLORED_PIXELS_ON_BLACK = 1
    RANDOM_WHITE_PIXELS_ON_CHANGING_BACKGROUND = 2
    VERTICAL_RAINBOW = 3
    DIAGONAL_RIGHT_RAINBOW = 4
    DIAGONAL_LEFT_RAINBOW_ON_BLACK = 5
    RANDOM_COLORED_PIXELS = 6


class EffectModule(IDotMatrixModule):
    """This class contains the Effect controls for the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def show(
        self,
        style: EffectStyle | int,
        colors: List[Tuple[int, int, int] or int or str],
    ):
        """
        Set the effect mode of the device.

        Args:
            style (int): Style of the effect 0-6.
            colors (list[tuple[int, int, int]]): list of red, green, blue tuples 2-7.
        """
        if isinstance(style, EffectStyle):
            style = style.value

        if style not in range(0, 7):
            raise ValueError("effect.setMode expects parameter style to be between 0 and 6")

        if len(colors) not in range(2, 8):
            raise ValueError("effect.setMode expects parameter rgb_values to be a list of tuples to be between 2 and 7")

        colors = color_utils.parse_color_rgb_list(colors)

        for rgb in colors:
            for r, g, b in [rgb]:
                if r not in range(0, 256) or g not in range(0, 256) or b not in range(0, 256):
                    raise ValueError(
                        "effect.setMode expects parameter rgb_values to be a list of tuples of red, green, blue values between 0 and 255")

        data = self._compute_payload(style=style, rgb_values=colors)
        await self._send_bytes(data=data)

    @staticmethod
    def _compute_payload(style, rgb_values) -> bytearray:
        """
        Computes the payload for the effect mode command.

        Args:
            style (int): The effect style, must be between 0 and 6.
            rgb_values (list[tuple[int, int, int]]): List of RGB tuples, each tuple contains red, green, and blue values.
        """
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

        return data
