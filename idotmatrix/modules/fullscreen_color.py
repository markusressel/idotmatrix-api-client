import logging
from asyncio import sleep
from typing import Tuple

from idotmatrix.modules import IDotMatrixModule


class FullscreenColorModule(IDotMatrixModule):
    """
    This class contains the management of the iDotMatrix fullscreen color mode.
    Based on the BleProtocolN.java file of the iDotMatrix Android App.
    """

    logging = logging.getLogger(__name__)

    async def show_color(
        self, color: Tuple[int, int, int] or int or str
    ):
        """
        Sets the fullscreen color of the screen of the device.
        Args:
            color (tuple or str): Color in RGB format as a tuple of three integers (r, g, b) or a string in hex format (#RRGGBB or 0xRRGGBB).
        """
        if isinstance(color, int):
            if not (0 <= color < 16777216):
                raise ValueError("Color integer must be between 0 and 16777215 (0xFFFFFF)")
            # Convert integer to RGB tuple
            r = (color >> 16) & 0xFF
            g = (color >> 8) & 0xFF
            b = color & 0xFF
            color = (r, g, b)
        elif isinstance(color, str):
            if color.startswith("#"):
                # Convert hex color to RGB
                color = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
            elif color.startswith("0x"):
                # Convert hex color with '0x' prefix to RGB
                color = tuple(int(color[i:i + 2], 16) for i in (2, 4, 6))
            else:
                try:
                    from matplotlib import colors
                    color = colors.to_rgb(color)
                except:
                    raise ValueError(
                        "Invalid color string. Use hex format (#RRGGBB), '0xRRGGBB', or a named color."
                    )
        await self._show_color_rgb(*color)

    async def _show_color_rgb(
        self, r: int = 0, g: int = 0, b: int = 0
    ):
        """
        Sets the fullscreen color of the screen of the device

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

        data = self._create_payload(
            r=r, g=g, b=b
        )
        await self._send_bytes(data=data)
        await sleep(0.02)  # wait for the device to process the command

    @staticmethod
    def _create_payload(r, g, b) -> bytearray:
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
        return data
