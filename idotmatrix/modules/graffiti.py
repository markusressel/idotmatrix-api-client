import logging

from idotmatrix.modules import IDotMatrixModule
from idotmatrix.util import color_utils

MAX_PIXEL_LIST_LENGTH = 255  # trial and error


class GraffitiModule(IDotMatrixModule):
    """This class contains the Graffiti controls for the iDotMatrix device."""

    logging = logging.getLogger(__name__)

    async def set_pixel(
        self,
        color: tuple[int, int, int] or int or str,
        xy: tuple[int, int],
    ):
        """
        Set a pixel on the device to the given color

        Args:
            color (tuple or str): Color in RGB format as a tuple of three integers (r, g, b) or a string in hex format (#RRGGBB or 0xRRGGBB).
            xy (tuple): Coordinates on the screen as a tuple of two integers (x, y).
        """
        color = color_utils.parse_color_rgb(color)
        data = self._create_payload(
            r=color[0], g=color[1], b=color[2],
            xys=[xy]
        )

        await self._send_bytes(data=data, sleep_after=0.02)

    async def set_pixels(
            self,
            color: tuple[int, int, int] or int or str,
            xys: list[tuple[int, int]]
    ):
        """
        Set multiple pixels on the device to the given color

        Args:
            color (tuple or str): Color in RGB format as a tuple of three integers (r, g, b) or a string in hex format (#RRGGBB or 0xRRGGBB).
            xys (list of tuples): List of coordinates on the screen as tuples of two integers (x, y).
        """
        color = color_utils.parse_color_rgb(color)
        data = self._create_payload(
            r=color[0], g=color[1], b=color[2],
            xys=xys
        )

        # using response=True here works better than trying to time the sleep
        await self._send_bytes(data=data, response=True)

    @staticmethod
    def _create_payload(
        r: int, g: int, b: int,
        xys: list[tuple[int, int]]
    ) -> bytearray:
        if len(xys) > MAX_PIXEL_LIST_LENGTH:
            raise ValueError("xys coordinate list must have length <= {}".format(MAX_PIXEL_LIST_LENGTH))

        size = 8 + 2*len(xys)
        data = bytearray(
            [
                size % 256,   # length of the array, LSB
                size // 256,  # length of the array, MSB (will be 0 or 1)
                5,            # graffiti mode
                1,            # mirroring mode 1-4; TODO: support these
                0,            # ???
                r % 256,      # Ensure R, G, B, X, Y are within byte range
                g % 256,
                b % 256,
            ] + [0] * (size - 8)
        )
        for i, xy in enumerate(xys):
            data[8+2*i] = xy[0]
            data[8+2*i+1] = xy[1]
        return data
