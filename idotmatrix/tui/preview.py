import os
import struct
import sys

from PIL import Image as PILImage
from rich.style import Style
from rich.text import Text
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

try:
    import fcntl
    import termios
except ImportError:  # not on Windows
    fcntl = termios = None

HALF_BLOCK = "▀"
DEFAULT_CELL_ASPECT = 2.0
# cells at least this much taller than wide get two columns per pixel; in between the pixels are slightly too tall
WIDE_PIXEL_ASPECT = 3.0


def cell_aspect() -> float:
    """
    Height of a terminal cell divided by its width. Asked from the terminal (if it reports its size in pixels),
    or taken from `IDOTMATRIX_TUI_CELL_ASPECT`, or 2.0.
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


def columns_per_pixel(aspect: float) -> int:
    """
    How many columns a pixel of a half block picture gets. Always the same for all pixels: a pixel that is one column
    wide in some places and two in others looks worse than pixels that are all a little too tall.
    """
    return 2 if aspect >= WIDE_PIXEL_ASPECT else 1


def fitted_side(image_side: int, max_columns: int, max_rows: int, aspect: float = 2.0) -> int:
    """How many pixels per side of the picture fit in the space."""
    return max(1, min(image_side, max_columns // columns_per_pixel(aspect), max_rows * 2))


def render_frame(image: PILImage.Image, max_columns: int, max_rows: int, aspect: float = 2.0) -> Text:
    """
    Draws a picture with half blocks, two pixels on top of each other in a cell. The picture is scaled down (not up
    beyond a whole pixel) to fit. Exact only if a cell is twice as high as wide, see `columns_per_pixel`, and
    `detect_pixel_image` for the exact way.
    """
    per_pixel = columns_per_pixel(aspect)
    side = fitted_side(image.width, max_columns, max_rows, aspect)
    if side != image.width or side != image.height:
        image = image.resize((side, side), PILImage.Resampling.NEAREST)
    image = image.convert("RGB")
    pixels = image.load()
    columns = side * per_pixel
    text = Text(no_wrap=True, overflow="crop")
    for y in range(0, side, 2):
        for column in range(columns):
            x = column // per_pixel
            top = pixels[x, y]
            bottom = pixels[x, y + 1] if y + 1 < side else (0, 0, 0)
            text.append(HALF_BLOCK, Style(color=f"rgb({top[0]},{top[1]},{top[2]})",
                                          bgcolor=f"rgb({bottom[0]},{bottom[1]},{bottom[2]})"))
        if y + 2 < side:
            text.append("\n")
    return text


class Fitted(Message):
    """The picture was drawn with `shown` pixels per side of the `actual` ones (equal if it fits, 0 if no picture)."""

    def __init__(self, shown: int, actual: int):
        super().__init__()
        self.shown = shown
        self.actual = actual


class _Player:
    """Plays frames with their durations. A widget that draws them implements `_draw`."""

    def _init_player(self) -> None:
        self._frames: list[PILImage.Image] = []
        self._durations: list[int] = []
        self._index = 0
        self._timer = None
        self._paused = False

    def show_frames(self, frames: list[PILImage.Image], durations: list[int]) -> None:
        self._stop()
        self._frames, self._durations, self._index = frames, durations, 0
        self._draw()
        if len(frames) > 1 and not self._paused:
            self._schedule()

    def on_resize(self) -> None:
        if self._frames:
            self._draw()

    def pause(self) -> None:
        """Stops playing, f.e. while another page is shown: drawing the frames takes time the page could use."""
        self._paused = True
        self._stop()

    def resume(self) -> None:
        self._paused = False
        if len(self._frames) > 1 and self._timer is None:
            self._schedule()

    def _stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _schedule(self) -> None:
        self._timer = self.set_timer(max(self._durations[self._index], 20) / 1000, self._next)

    def _next(self) -> None:
        if not self._frames:  # the timer fired as the picture was replaced
            return
        self._index = (self._index + 1) % len(self._frames)
        self._draw()
        if not self._paused:
            self._schedule()

    def _draw(self) -> None:
        raise NotImplementedError


class PreviewWidget(_Player, Static):
    """Shows a picture with half blocks, or plays an animation with the durations of its frames."""

    DEFAULT_CSS = """
    PreviewWidget {
        content-align: center middle;
        height: 1fr;
    }
    """
    Fitted = Fitted

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._init_player()
        self._aspect = cell_aspect()

    def show_message(self, message: str) -> None:
        self._stop()
        self._frames, self._durations = [], []
        self.update(message)
        self.post_message(Fitted(0, 0))

    def _draw(self) -> None:
        size = self.size
        if size.width and size.height:
            actual = self._frames[self._index].width
            self.post_message(Fitted(fitted_side(actual, size.width, size.height, self._aspect), actual))
            self.update(render_frame(self._frames[self._index], size.width, size.height, self._aspect))


def detect_pixel_image():
    """
    The widget class that draws real pixels (Kitty graphics or Sixel), or None if the terminal supports none of them
    or `IDOTMATRIX_TUI_PIXELS=off`. Asks the terminal, so call it before the app starts.
    """
    if os.environ.get("IDOTMATRIX_TUI_PIXELS", "").lower() in ("off", "0", "no", "false"):
        return None
    try:
        from textual_image import renderable, widget
    except ImportError:
        return None
    if renderable.Image is renderable.SixelImage:
        return widget.SixelImage
    if renderable.Image is renderable.TGPImage:
        return widget.TGPImage
    return None


class PixelPreviewWidget(_Player, Vertical):
    """
    Shows a picture with real pixels, exactly square whatever the shape of the cells. The picture is enlarged by a
    whole number first (nearest neighbour), so the pixels stay sharp.
    """

    DEFAULT_CSS = """
    PixelPreviewWidget { height: 1fr; align: center middle; }
    PixelPreviewWidget > .pixels { width: auto; height: auto; max-width: 100%; max-height: 100%; }
    PixelPreviewWidget > .message { width: auto; height: auto; }
    """
    Fitted = Fitted

    def __init__(self, image_class, **kwargs):
        super().__init__(**kwargs)
        self._init_player()
        self._image_class = image_class
        self._pixels = None
        self._label = Static("", classes="message")

    def compose(self):
        self._pixels = self._image_class(classes="pixels")
        self._pixels.display = False
        yield self._pixels
        yield self._label

    def show_message(self, message: str) -> None:
        self._stop()
        self._frames, self._durations = [], []
        self._pixels.display = False
        self._pixels.image = None
        self._label.display = True
        self._label.update(message)
        self.post_message(Fitted(0, 0))

    def _draw(self) -> None:
        size = self.size
        if not (size.width and size.height):
            return
        from textual_image.widget import get_cell_size
        cell = get_cell_size()
        frame = self._frames[self._index]
        side = frame.width
        room = min(size.width * cell.width, size.height * cell.height)
        factor = max(1, room // side)
        self.post_message(Fitted(min(side, room), side))
        self._label.display = False
        self._pixels.display = True
        self._pixels.image = frame.convert("RGB").resize((side * factor, side * factor), PILImage.Resampling.NEAREST)
