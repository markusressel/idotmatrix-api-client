import logging
import zlib
from enum import Enum
from typing import Tuple, Optional

from PIL import Image, ImageDraw, ImageFont

from idotmatrix.modules import IDotMatrixModule
from idotmatrix.util import color_utils


class TextMode(Enum):
    REPLACE = 0
    MARQUEE = 1
    REVERSED_MARQUEE = 2
    VERTICAL_RISING_MARQUEE = 3
    VERTICAL_LOWERING_MARQUEE = 4
    BLINKING = 5
    FADING = 6
    TETRIS = 7
    FILLING = 8


class TextColorMode(Enum):
    WHITE = 0
    RGB = 1
    RAINBOW_1 = 2
    RAINBOW_2 = 3
    RAINBOW_3 = 4
    RAINBOW_4 = 5


class TextModule(IDotMatrixModule):
    """Manages text processing and packet creation for iDotMatrix devices. With help from https://github.com/8none1/idotmatrix/ :)"""

    logging = logging.getLogger(__name__)
    # must be 16x32 or 8x16
    image_width = 16
    image_height = 32
    # must be x05 for 16x32 or x02 for 8x16
    separator = b"\x05\xff\xff\xff"

    async def show_text(
        self,
        text: str,
        font_size: int = 16,
        font_path: Optional[str] = None,
        text_mode: TextMode | int = TextMode.MARQUEE,
        speed: int = 95,
        text_color_mode: TextColorMode | int = TextColorMode.WHITE,
        text_color: Tuple[int, int, int] or int or str = None,
        text_bg_color: Optional[Tuple[int, int, int] or int or str] = None,
    ):
        """
        Displays text on the iDotMatrix device with specified settings.
        Args:
            text (str): The text to display.
            font_size (int): Size of the font. Defaults to 16.
            font_path (Optional[str]): Path to the font file. Defaults to None, which uses a default font.
            text_mode (TextMode | int): Mode for displaying text. Defaults to TextMode.MARQUEE.
            speed (int): Speed of the text display. Defaults to 95.
            text_color_mode (TextColorMode | int): Color mode for the text. Defaults to TextColorMode.WHITE.
            text_color (Tuple[int, int, int]): RGB color for the text. Defaults to None, which uses white.
            text_bg_color (Optional[Tuple[int, int, int]]): RGB color for the background. Defaults to None, which uses black.
        Raises:
            ValueError: If text_color is None and text_color_mode is RGB.
        Raises:
            TypeError: If text_mode or text_color_mode is not an instance of TextMode or TextColorMode.
        Raises:
            ValueError: If text_color is None when text_color_mode is RGB.
        """
        if isinstance(text_mode, TextMode):
            text_mode = text_mode.value

        if isinstance(text_color_mode, TextColorMode):
            text_color_mode = text_color_mode.value

        if text_color is None:
            if text_color_mode == TextColorMode.RGB.value:
                raise ValueError("text_color must be provided when text_color_mode is RGB")
            text_color = (255, 255, 255)
        else:
            text_color = color_utils.parse_color_rgb(text_color)

        text_bg_mode = 0 if text_bg_color is None else 1
        if text_bg_color is None:
            text_bg_color = (0, 0, 0)
        else:
            text_bg_color = color_utils.parse_color_rgb(text_bg_color)

        data = self._build_string_packet(
            text_mode=text_mode,
            speed=speed,
            text_color_mode=text_color_mode,
            text_color=text_color,
            text_bg_mode=text_bg_mode,
            text_bg_color=text_bg_color,
            text_bitmaps=self._string_to_bitmaps(
                text=text,
                font_size=font_size,
                font_path=font_path,
            ),
        )
        await self._send_bytes(data=data)

    def _build_string_packet(
        self,
        text_bitmaps: bytearray,
        text_mode: int,
        speed: int = 95,
        text_color_mode: int = 0,
        text_color: Tuple[int, int, int] = (255, 255, 255),
        text_bg_mode: int = 0,
        text_bg_color: Tuple[int, int, int] = (0, 255, 0),
    ) -> bytearray:
        """Constructs a packet with the settings and bitmaps for iDotMatrix devices.

        Args:
            text_bitmaps (bytearray): bitmap list of the text characters
            text_mode (int, optional): Text mode. 0 = replace text, 1 = marquee, 2 = reversed marquee, 3 = vertical rising marquee, 4 = vertical lowering marquee, 5 = blinking, 6 = fading, 7 = tetris, 8 = filling
            speed (int, optional): Speed of Text. Defaults to 95.
            text_color_mode (int, optional): Text Color Mode. Defaults to 0. 0 = white, 1 = use given RGB color, 2,3,4,5 = rainbow modes
            text_color (Tuple[int, int, int], optional): Text RGB Color. Defaults to (255, 0, 0).
            text_bg_mode (int, optional): Text Background Mode. Defaults to 0. 0 = black, 1 = use given RGB color
            text_bg_color (Tuple[int, int, int], optional): Background RGB Color. Defaults to (0, 0, 0).

        Returns:
            bytearray: A bytearray containing the complete packet to be sent to the iDotMatrix device.
        """
        num_chars = text_bitmaps.count(self.separator)

        text_metadata = bytearray(
            [
                0,
                0,  # Placeholder for num_chars, to be set below
                0,
                1,  # Static values
                text_mode,
                speed,
                text_color_mode,
                *text_color,
                text_bg_mode,
                *text_bg_color,
            ]
        )
        text_metadata[:2] = num_chars.to_bytes(2, byteorder="little")

        packet = text_metadata + text_bitmaps

        header = bytearray(
            [
                0,
                0,  # total_len placeholder
                3,
                0,
                0,  # Static header values
                0,
                0,
                0,
                0,  # Placeholder for packet length
                0,
                0,
                0,
                0,  # Placeholder for CRC
                0,
                0,
                12,  # Static footer values
            ]
        )
        total_len = len(packet) + len(header)
        header[:2] = total_len.to_bytes(2, byteorder="little")
        header[5:9] = len(packet).to_bytes(4, byteorder="little")
        header[9:13] = zlib.crc32(packet).to_bytes(4, byteorder="little")

        return header + packet

    def _string_to_bitmaps(
        self, text: str, font_path: Optional[str] = None, font_size: Optional[int] = 20
    ) -> bytearray:
        """Converts text to bitmap images suitable for iDotMatrix devices."""
        if not font_path:
            # using open source font from https://www.fontspace.com/rain-font-f22577
            font_path = "./fonts/Rain-DRM3.otf"
        font = ImageFont.truetype(font_path, font_size)
        byte_stream = bytearray()
        for char in text:
            # todo make image the correct size for 16x16, 32x32 and 64x64
            image = Image.new("1", (self.image_width, self.image_height), 0)
            draw = ImageDraw.Draw(image)
            _, _, text_width, text_height = draw.textbbox((0, 0), text=char, font=font)
            text_x = (self.image_width - text_width) // 2
            text_y = (self.image_height - text_height) // 2
            draw.text((text_x, text_y), char, fill=1, font=font)
            bitmap = bytearray()
            for y in range(self.image_height):
                for x in range(self.image_width):
                    if x % 8 == 0:
                        byte = 0
                    pixel = image.getpixel((x, y))
                    byte |= (pixel & 1) << (x % 8)
                    if x % 8 == 7 or x == self.image_width - 1:
                        bitmap.append(byte)
            byte_stream.extend(self.separator + bitmap)
        return byte_stream
