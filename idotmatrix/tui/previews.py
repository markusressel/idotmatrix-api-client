"""What the text and the effects of the controls page look like, drawn with half blocks."""
import colorsys
import logging
import math
import random

from rich.style import Style
from rich.text import Text
from textual.widgets import Static

from idotmatrix.modules.effect import EffectStyle
from idotmatrix.modules.text import TextModule

logging = logging.getLogger(__name__)

Color = tuple[int, int, int]
BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)
SEPARATORS = {0x02: (8, 16), 0x05: (16, 32)}  # the first byte of the separator in front of a character -> its cell
MAX_CHARACTERS = 16
# the top half of a 64x64 display, so a stripe is as wide as on the display
EFFECT_WIDTH, EFFECT_HEIGHT = 64, 32
LEFT_STRIPE = 4  # the width of a stripe of the diagonal left rainbow along a row, and of the gap (verified)
LEFT_PERIOD = 2 * LEFT_STRIPE
VERTICAL_BAND = 4  # the width of a stripe of the vertical rainbow (verified)
DIAGONAL_BAND = 5  # the width of a stripe of the diagonal rainbow in pixels along a row (a guess)


def style_of(color: Color) -> str:
    return "rgb({},{},{})".format(*color)


def half_blocks(pixels: list[list[Color]]) -> Text:
    """Rows of pixels as text, two rows of pixels in one row of cells."""
    text = Text(no_wrap=True, overflow="crop")
    for y in range(0, len(pixels), 2):
        top = pixels[y]
        bottom = pixels[y + 1] if y + 1 < len(pixels) else [BLACK] * len(top)
        for upper, lower in zip(top, bottom):
            text.append("▀", Style(color=style_of(upper), bgcolor=style_of(lower)))
        if y + 2 < len(pixels):
            text.append("\n")
    return text


def decode_characters(stream: bytes) -> tuple[list[list[list[int]]], tuple[int, int]]:
    """The characters the device is sent (`TextModule._string_to_bitmaps`) as rows of 0 and 1, and their cell size."""
    characters = []
    cell = (8, 16)
    position = 0
    while position + 4 <= len(stream):
        cell = SEPARATORS.get(stream[position], cell)
        width, height = cell
        position += 4
        per_row = (width + 7) // 8
        rows = []
        for _ in range(height):
            row = []
            for byte_index in range(per_row):
                byte = stream[position + byte_index]
                row.extend((byte >> bit) & 1 for bit in range(8))
            rows.append(row[:width])
            position += per_row
        characters.append(rows)
    return characters, cell


def text_color(mode: int, color: Color, x: int, total: int) -> Color:
    """The color of a pixel of the text. The rainbow modes are approximations of what the device does."""
    if mode == 0:
        return WHITE
    if mode == 1:
        return color
    hue = (x / max(total, 1)) * (1.0 if mode in (2, 4) else 0.5) + (0.0 if mode in (2, 3) else 0.3)
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, 1.0, 1.0)
    return round(red * 255), round(green * 255), round(blue * 255)


def render_text(text: str, font_size: int, color_mode: int, color: Color, background: Color | None,
                columns: int = 64) -> tuple[Text, str]:
    """The text as the device shows it: its cells side by side, as many as fit on a display `columns` wide."""
    stream = TextModule(connection_manager=None)._string_to_bitmaps(text[:MAX_CHARACTERS], font_size=font_size)
    characters, (width, height) = decode_characters(bytes(stream))
    shown = max(columns // width, 1)
    characters = characters[:shown]
    total = len(characters) * width
    bg = background or BLACK
    pixels = [[bg] * (shown * width) for _ in range(height)]
    for index, rows in enumerate(characters):
        for y, row in enumerate(rows):
            for x, bit in enumerate(row):
                if bit:
                    pixels[y][index * width + x] = text_color(color_mode, color, index * width + x, total)
    note = f"cells of {width}x{height}, {shown} fit on the display"
    if len(text) > shown:
        note += f", the text scrolls or is cut after {shown}"
    return half_blocks(pixels), note


class TextPreview(Static):
    """The text with its font and size, in its colors."""

    DEFAULT_CSS = """
    TextPreview { height: auto; margin-top: 1; padding: 0 1; border: round $primary-darken-1;
                  border-title-color: $primary; }
    """

    def on_mount(self) -> None:
        self.border_title = "Preview"

    def show(self, values: dict) -> None:
        try:
            columns = self.app.canvas_size
            text, note = render_text(values["text"], values["font_size"], values["color_mode"], values["color"],
                                     values.get("background"), columns)
        except Exception as e:  # a font size the font cannot draw, an empty text
            logging.debug("no preview", exc_info=True)
            self.update(Text(str(e), style="dim"))
            return
        text.append("\n" + note, style="dim")
        self.update(text)


def mix(colors: list[Color], position: float) -> Color:
    """A color along a loop through the colors."""
    position %= 1.0
    scaled = position * len(colors)
    index = int(scaled)
    fraction = scaled - index
    first, second = colors[index % len(colors)], colors[(index + 1) % len(colors)]
    return tuple(round(a + (b - a) * fraction) for a, b in zip(first, second))


class EffectPreview(Static):
    """The effect of the controls page, moving. It is an approximation: what the display draws is not documented."""

    DEFAULT_CSS = """
    EffectPreview { height: auto; margin-top: 1; padding: 0 1; border: round $primary-darken-1;
                    border-title-color: $primary; }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._style = 0
        self._colors: list[Color] = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
        self._phase = 0.0
        self._random = random.Random()
        self._grid: list[list[Color]] = []
        self._fill_grid()

    def _fill_grid(self) -> None:
        """Every pixel has a color from the start, like on the display."""
        self._grid = [[self._random.choice(self._colors) for _ in range(EFFECT_WIDTH)] for _ in range(EFFECT_HEIGHT)]

    def on_mount(self) -> None:
        self.border_title = "Preview (top half, an approximation)"
        self.set_interval(0.1, self._tick)
        self._tick()

    def show(self, values: dict) -> None:
        self._style = values["style"]
        colors = list(values["colors"])
        if colors != self._colors:
            self._colors = colors
            self._fill_grid()  # no pixel keeps a color that was removed
        self._tick()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.02) % 1.0
        self.update(half_blocks(self._frame()))

    def _frame(self) -> list[list[Color]]:
        width, height, colors, phase = EFFECT_WIDTH, EFFECT_HEIGHT, self._colors, self._phase
        style = self._style
        pick = self._random.choice
        if style == EffectStyle.GRADIENT_HORIZONTAL_RAINBOW.value:
            # smooth horizontal stripes that move down (verified)
            return [[mix(colors, y / height - phase)] * width for y in range(height)]
        if style == EffectStyle.VERTICAL_RAINBOW.value:
            # hard vertical stripes that move to the right (verified)
            offset = round(phase * len(colors) * VERTICAL_BAND)
            return [[colors[((x - offset) // VERTICAL_BAND) % len(colors)] for x in range(width)]
                    for _ in range(height)]
        if style == EffectStyle.DIAGONAL_RIGHT_RAINBOW.value:
            # hard stripes without blending that run from the top left to the bottom right and move to the top
            # right (verified)
            offset = round(phase * len(colors) * DIAGONAL_BAND)
            return [[colors[((x - y - offset) // DIAGONAL_BAND) % len(colors)] for x in range(width)]
                    for y in range(height)]
        if style == EffectStyle.DIAGONAL_LEFT_RAINBOW_ON_BLACK.value:
            # single colored stripes from the bottom left to the top right with black between them, moving to the
            # top left (verified)
            offset = round(phase * len(colors) * LEFT_PERIOD)
            return [[colors[((x + y + offset) // LEFT_PERIOD) % len(colors)]
                     if (x + y + offset) % LEFT_PERIOD < LEFT_STRIPE else BLACK
                     for x in range(width)] for y in range(height)]
        if style == EffectStyle.RANDOM_COLORED_PIXELS_ON_BLACK.value:
            return [[pick(colors) if self._random.random() < 0.12 else BLACK for _ in range(width)]
                    for _ in range(height)]
        if style == EffectStyle.RANDOM_WHITE_PIXELS_ON_CHANGING_BACKGROUND.value:
            background = mix(colors, phase)
            return [[WHITE if self._random.random() < 0.08 else background for _ in range(width)]
                    for _ in range(height)]
        # random colored pixels: a few change in every frame
        for _ in range(width * height // 12):
            self._grid[self._random.randrange(height)][self._random.randrange(width)] = pick(colors)
        return [row[:] for row in self._grid]
