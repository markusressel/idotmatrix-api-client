import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from idotmatrix.util import color_utils

# a pixel font that is crisp at 8 px (bundled, its license is PixelOperator-License.txt in the same folder)
DEFAULT_FONT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts", "16-PixelOperator8.ttf"))

POSITIONS = (
    "top-left", "top-center", "top-right",
    "center",
    "bottom-left", "bottom-center", "bottom-right",
)


@lru_cache(maxsize=16)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@dataclass(frozen=True)
class TextOverlay:
    """
    A text that is drawn on top of a picture or of every frame of an animation, at the size of the screen, before the
    colors are reduced. It does not change over time: for a clock or an album title upload again when it changes.

    Attributes:
        text: What to write.
        position: Where the text goes: one of `POSITIONS`.
        color: The color of the text, anything `color_utils.parse_color_rgb` accepts.
        background: A box behind the text so that it is readable on any picture, (R, G, B, alpha) with alpha from 0
            (invisible) to 255, or None for no box.
        font_size: The size of the font in pixels. The default font is made for 8, which fits about 10 characters on
            a 64 pixel wide screen, a longer text is cut.
        font: The path of a font file, a pixel font that is bundled is used if not given.
        margin: The distance to the border of the screen in pixels.
    """
    text: str
    position: str = "bottom-left"
    color: Tuple[int, int, int] | int | str = (255, 255, 255)
    background: Tuple[int, int, int, int] | None = (0, 0, 0, 160)
    font_size: int = 8
    font: str | None = None
    margin: int = 1

    def __post_init__(self):
        if not self.text:
            raise ValueError("text must not be empty")
        if self.position not in POSITIONS:
            raise ValueError(f"position must be one of {', '.join(POSITIONS)}, got: {self.position!r}")
        if not isinstance(self.font_size, int) or isinstance(self.font_size, bool) or self.font_size < 4:
            raise ValueError(f"font_size must be at least 4, got: {self.font_size!r}")
        if self.background is not None and (len(self.background) != 4 or not all(0 <= v <= 255 for v in self.background)):
            raise ValueError(f"background must be (R, G, B, alpha) with values from 0 to 255, got: {self.background!r}")
        if not isinstance(self.margin, int) or isinstance(self.margin, bool) or self.margin < 0:
            raise ValueError(f"margin must not be negative, got: {self.margin!r}")
        color_utils.parse_color_rgb(self.color)

    def apply(self, frame: Image.Image) -> Image.Image:
        """Returns the frame (any mode, as large as the screen) with the text on top, as RGBA."""
        frame = frame.convert("RGBA")
        font = _font(self.font or DEFAULT_FONT, self.font_size)
        measure = ImageDraw.Draw(frame)
        pad = 1 if self.background else 0
        room = frame.width - 2 * self.margin - 2 * pad

        # a text that is too wide for the screen is cut, there is nothing to scroll
        text = self.text
        left, top, right, bottom = measure.textbbox((0, 0), text, font=font)
        while right - left > room and len(text) > 1:
            text = text[:-1]
            left, top, right, bottom = measure.textbbox((0, 0), text, font=font)
        box_width, box_height = right - left + 2 * pad, bottom - top + 2 * pad

        if self.position == "center":
            vertical, horizontal = "center", "center"
        else:
            vertical, horizontal = self.position.split("-")
        x = {"left": self.margin, "center": (frame.width - box_width) // 2,
             "right": frame.width - box_width - self.margin}[horizontal]
        y = {"top": self.margin, "center": (frame.height - box_height) // 2,
             "bottom": frame.height - box_height - self.margin}[vertical]

        layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        if self.background:
            draw.rectangle((x, y, x + box_width - 1, y + box_height - 1), fill=self.background)
        draw.fontmode = "1"  # no anti-aliasing, the pixels of a pixel font stay sharp
        draw.text((x + pad - left, y + pad - top), text, font=font, fill=color_utils.parse_color_rgb(self.color))
        return Image.alpha_composite(frame, layer)
