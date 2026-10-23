import os
import struct
import sys

from PIL import Image as PILImage
from rich.style import Style
from rich.text import Text
from textual.widgets import Static

try:
    import fcntl
    import termios
except ImportError:  # not on Windows
    fcntl = termios = None

HALF_BLOCK = "▀"
DEFAULT_CELL_ASPECT = 2.2


def cell_aspect() -> float:
    """
    Height of a terminal cell divided by its width. Asked from the terminal (if it reports its size in pixels),
    or taken from `IDOTMATRIX_TUI_CELL_ASPECT`, or a typical 2.2.
    """
    try:
        value = float(os.environ.get("IDOTMATRIX_TUI_CELL_ASPECT", ""))
        if 1 <= value <= 4:
            return value
    except ValueError:
        pass
    for fd in (sys.__stdout__, sys.__stdin__) if fcntl else ():
        try:
            rows, columns, width, height = struct.unpack(
                "HHHH", fcntl.ioctl(fd.fileno(), termios.TIOCGWINSZ, b"\0" * 8))
            if rows and columns and width and height:
                value = (height / rows) / (width / columns)
                if 1 <= value <= 4:
                    return value
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    return DEFAULT_CELL_ASPECT


def render_frame(image: PILImage.Image, max_columns: int, max_rows: int, aspect: float = 2.0) -> Text:
    """
    Draws a picture with half blocks, two pixels on top of each other in a cell. A pixel is as wide as it is high
    (a half cell is `aspect / 2` cells wide), so the picture is square. The picture is scaled down (not up beyond a
    whole pixel) to fit.
    """
    per_pixel = aspect / 2
    side = max(1, min(image.width, int(max_columns / per_pixel), max_rows * 2))
    if side != image.width or side != image.height:
        image = image.resize((side, side), PILImage.Resampling.NEAREST)
    image = image.convert("RGB")
    pixels = image.load()
    columns = max(1, round(side * per_pixel))
    text = Text(no_wrap=True, overflow="crop")
    for y in range(0, side, 2):
        for column in range(columns):
            x = min(int(column / per_pixel), side - 1)
            top = pixels[x, y]
            bottom = pixels[x, y + 1] if y + 1 < side else (0, 0, 0)
            text.append(HALF_BLOCK, Style(color=f"rgb({top[0]},{top[1]},{top[2]})",
                                          bgcolor=f"rgb({bottom[0]},{bottom[1]},{bottom[2]})"))
        if y + 2 < side:
            text.append("\n")
    return text


class PreviewWidget(Static):
    """Shows a picture, or plays an animation with the durations of its frames."""

    DEFAULT_CSS = """
    PreviewWidget {
        content-align: center middle;
        height: 1fr;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._frames: list[PILImage.Image] = []
        self._durations: list[int] = []
        self._index = 0
        self._timer = None
        self._aspect = cell_aspect()

    def show_message(self, message: str) -> None:
        self._stop()
        self._frames, self._durations = [], []
        self.update(message)

    def show_frames(self, frames: list[PILImage.Image], durations: list[int]) -> None:
        self._stop()
        self._frames, self._durations, self._index = frames, durations, 0
        self._draw()
        if len(frames) > 1:
            self._schedule()

    def on_resize(self) -> None:
        if self._frames:
            self._draw()

    def _stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _draw(self) -> None:
        size = self.size
        if size.width and size.height:
            self.update(render_frame(self._frames[self._index], size.width, size.height, self._aspect))

    def _schedule(self) -> None:
        self._timer = self.set_timer(max(self._durations[self._index], 20) / 1000, self._next)

    def _next(self) -> None:
        self._index = (self._index + 1) % len(self._frames)
        self._draw()
        self._schedule()
