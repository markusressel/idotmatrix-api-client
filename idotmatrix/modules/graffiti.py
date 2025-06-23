import logging

from idotmatrix.modules import IDotMatrixModule
from idotmatrix.util import color_utils


class GraffitiModule(IDotMatrixModule):
    """This class contains the Graffiti controls for the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def set_pixel(
        self,
        color: tuple[int, int, int] or int or str,
        xy: tuple[int, int],
    ):
        """
        Set the scoreboard of the device.

        Args:
            color (tuple or str): Color in RGB format as a tuple of three integers (r, g, b) or a string in hex format (#RRGGBB or 0xRRGGBB).
            xy (tuple): Coordinates on the screen as a tuple of two integers (x, y).
        """
        color = color_utils.parse_color_rgb(color)
        data = self._create_payload(
            r=color[0], g=color[1], b=color[2],
            x=xy[0], y=xy[1]
        )

        await self._send_bytes(data=data, sleep_after=0.02)

    @staticmethod
    def _create_payload(
        r: int, g: int, b: int,
        x: int, y: int
    ) -> bytearray:
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
        return data
