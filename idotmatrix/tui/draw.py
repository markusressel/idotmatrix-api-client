import asyncio
import logging
from functools import lru_cache
from itertools import islice
from pathlib import Path

from PIL import Image as PILImage
from rich.color import Color as RichColor
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.geometry import Region, Size
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static

from idotmatrix.modules.graffiti import MAX_PIXEL_LIST_LENGTH
from idotmatrix.modules.image import ImageMode
from idotmatrix.tui.canvas import BLACK, Color, PixelCanvas
from idotmatrix.tui.dialogs import PathDialog, TextDialog
from idotmatrix.tui.pages import PageScreen
from idotmatrix.util.color_utils import parse_color_rgb

logging = logging.getLogger(__name__)

PALETTE = (
    "#ff0000", "#ff8000", "#ffff00", "#80ff00", "#00ff00", "#00ff80", "#00ffff", "#0080ff", "#0000ff", "#8000ff",
    "#ff00ff", "#ff0080", "#ffffff", "#c0c0c0", "#808080", "#804000", "#000000",
)
BIG_STEP = 8
STATE_DELAY_SECONDS = 0.05
ANCHOR: Color = (255, 215, 0)


def hex_of(color: Color) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def contrast(color: Color) -> Color:
    """A color that stands out against `color`: for the cursor."""
    brightness = (color[0] * 299 + color[1] * 587 + color[2] * 114) / 1000
    return (0, 0, 0) if brightness > 128 else (255, 255, 255)


def style_of(color: Color) -> str:
    return "rgb({},{},{})".format(*color)


@lru_cache(maxsize=16384)
def cell_style(top: Color, bottom: Color) -> Style:
    """The style of a cell with two pixels, cached: a canvas has thousands of them and few colors."""
    return Style(color=RichColor.from_rgb(*top), bgcolor=RichColor.from_rgb(*bottom))


class CanvasWidget(Widget):
    """
    The picture. If it fits, a pixel is two columns wide and one row high (square, and the mouse hits it exactly),
    otherwise two pixels share a cell with a half block (then the mouse paints the upper pixel, with Shift the lower).
    """

    DEFAULT_CSS = "CanvasWidget { width: auto; height: auto; }"
    ALLOW_SELECT = False  # dragging paints, it must not select text
    can_focus = True

    def __init__(self, canvas: PixelCanvas, **kwargs):
        super().__init__(**kwargs)
        self.canvas = canvas
        self.cursor = (canvas.size // 2, canvas.size // 2)
        self.anchor: tuple[int, int] | None = None
        self.wide = False
        self.on_pointer = None  # called with (x, y, button, started)
        self._pointer_down = False
        self._last_pixel: tuple[int, int] | None = None
        self._strips: dict[int, Strip] = {}
        self._shown_marks: set[int] = set()

    def get_content_width(self, container: Size, viewport: Size) -> int:
        return self.canvas.size * (2 if self.wide else 1)

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        return self.canvas.size if self.wide else (self.canvas.size + 1) // 2

    def set_wide(self, wide: bool) -> None:
        if wide != self.wide:
            self.wide = wide
            self.reset()

    def _color_at(self, x: int, y: int) -> Color:
        if (x, y) == self.cursor:
            return contrast(self.canvas.get(x, y))
        if (x, y) == self.anchor:
            return ANCHOR
        return self.canvas.get(x, y)

    def _cell_row(self, y: int) -> int:
        """The row of cells that shows the row of pixels."""
        return y if self.wide else y // 2

    def _marked_rows(self) -> set[int]:
        rows = {self._cell_row(self.cursor[1])}
        if self.anchor is not None:
            rows.add(self._cell_row(self.anchor[1]))
        return rows

    def render_line(self, row: int) -> Strip:
        """One row of cells. The rows are kept until a pixel in them changes, so a stroke draws a few of them."""
        strip = self._strips.get(row)
        if strip is None:
            size = self.canvas.size
            if self.wide:
                segments = [Segment("  ", cell_style(self._color_at(x, row), self._color_at(x, row)))
                            for x in range(size)] if row < size else []
            else:
                segments = [Segment("▀", cell_style(self._color_at(x, row * 2), self._color_at(x, row * 2 + 1)))
                            for x in range(size)] if row * 2 < size else []
            strip = self._strips[row] = Strip(segments)
        return strip

    def reset(self) -> None:
        """Draws everything again."""
        self._strips.clear()
        self.canvas.take_touched()
        self._shown_marks = self._marked_rows()
        self.refresh(layout=True)

    def update_rows(self) -> None:
        """Draws again the rows with changed pixels and the ones the cursor or the corner of a line is or was in."""
        rows = {self._cell_row(y) for y in self.canvas.take_touched()} | self._marked_rows() | self._shown_marks
        self._shown_marks = self._marked_rows()
        width = self.size.width
        for row in rows:
            self._strips.pop(row, None)
            self.refresh(Region(0, row, width, 1))

    # the mouse

    def _pixel(self, event: events.MouseEvent) -> tuple[int, int]:
        if self.wide:
            return event.x // 2, event.y
        return event.x, event.y * 2 + (1 if event.shift else 0)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._pointer_down = True
        self.capture_mouse()
        if self.on_pointer:
            self._last_pixel = self._pixel(event)
            self.on_pointer(*self._last_pixel, event.button, True)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._pointer_down and self.on_pointer:
            pixel = self._pixel(event)
            if pixel != self._last_pixel:  # many events arrive for one pixel
                self._last_pixel = pixel
                self.on_pointer(*pixel, event.button, False)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._pointer_down = False
        self.release_mouse()


class Palette(Static):
    """The colors to pick from: a click on one uses it."""

    ALLOW_SELECT = False
    CELL_WIDTH = 3
    PER_ROW = 5

    def on_click(self, event: events.Click) -> None:
        index = event.y * self.PER_ROW + event.x // self.CELL_WIDTH
        if 0 <= index < len(PALETTE) and event.x // self.CELL_WIDTH < self.PER_ROW:
            self.screen.action_palette(index)


class DrawScreen(PageScreen):
    """Draws pixels by hand, on the display as you go (the DIY mode) or all at once."""

    page_id = "draw"
    ALLOW_SELECT = False
    BINDINGS = [
        Binding("up", "move(0,-1)", "Move", show=False),
        Binding("down", "move(0,1)", "Move", show=False),
        Binding("left", "move(-1,0)", "Move", show=False),
        Binding("right", "move(1,0)", "Move", show=False),
        Binding("shift+up", f"move(0,-{BIG_STEP})", "Move", show=False),
        Binding("shift+down", f"move(0,{BIG_STEP})", "Move", show=False),
        Binding("shift+left", f"move(-{BIG_STEP},0)", "Move", show=False),
        Binding("shift+right", f"move({BIG_STEP},0)", "Move", show=False),
        Binding("space", "paint", "Paint"),
        Binding("enter", "pen", "Pen"),
        Binding("x,delete", "erase", "Erase"),
        Binding("f", "fill", "Fill"),
        Binding("l", "line", "Line"),
        Binding("b", "box", "Box"),
        Binding("p", "pick", "Pick"),
        Binding("c", "color", "Color"),
        Binding("left_square_bracket", "palette_step(-1)", "Previous color", show=False),
        Binding("right_square_bracket", "palette_step(1)", "Next color", show=False),
        Binding("u", "undo", "Undo"),
        Binding("y", "redo", "Redo"),
        Binding("k", "clear", "Clear"),
        Binding("a", "live", "Live"),
        Binding("s", "send", "Send"),
        Binding("v", "show", "Show"),
        Binding("o", "open", "Open"),
        Binding("w", "save", "Save"),
        Binding("escape", "cancel", "Cancel", show=False),
        *[Binding(str(number % 10), f"palette({number - 1})", show=False) for number in range(1, 11)],
    ]
    DEFAULT_CSS = """
    DrawScreen #draw { height: 1fr; padding: 0 1; }
    DrawScreen #canvas-box { width: 1fr; border: round $primary; border-title-color: $primary;
                             align: center middle; }
    DrawScreen #side { width: 34; margin-left: 1; }
    DrawScreen #palette-box, DrawScreen #state-box { border: round $primary-darken-1; border-title-color: $primary;
                                                    padding: 0 1; height: auto; }
    DrawScreen #state-box { margin-top: 1; }
    """

    def __init__(self):
        super().__init__()
        self.canvas: PixelCanvas | None = None
        self.color: Color = (255, 0, 0)
        self.pen_down = False
        self.live = True
        self.tool: str | None = None  # "line" or "box" while its first corner is set
        self._diy_active = False
        self._generation = -1
        self._wake: asyncio.Event | None = None
        self._widget: CanvasWidget | None = None
        self._state_timer = None

    @property
    def canvas_file(self) -> Path:
        return self.app.config_dir / "canvas.png"

    def content(self) -> ComposeResult:
        self.canvas = self._new_canvas()
        self._widget = CanvasWidget(self.canvas, id="canvas")
        self._widget.on_pointer = self._pointer
        with Horizontal(id="draw"):
            with Vertical(id="canvas-box") as box:
                box.border_title = f"Canvas {self.canvas.size}x{self.canvas.size}"
                yield self._widget
            with Vertical(id="side"):
                with Vertical(id="palette-box") as palette:
                    palette.border_title = "Colors"
                    yield Palette("", id="palette")
                with Vertical(id="state-box") as state:
                    state.border_title = "State"
                    yield Static("", id="state")

    def _new_canvas(self) -> PixelCanvas:
        canvas = PixelCanvas(self.app.canvas_size)
        try:
            with PILImage.open(self.canvas_file) as image:
                canvas.load(image)
            canvas.take_dirty()
        except (OSError, ValueError):
            pass
        return canvas

    def on_mount(self) -> None:
        self.color = parse_color_rgb(self.app.session.draw_color)
        self._wake = asyncio.Event()
        self.run_worker(self._sender(), name="draw", group="draw", exclusive=True)
        self._fit()
        self._update_palette()
        self._update()
        self._widget.focus()

    def on_screen_resume(self) -> None:
        if self.canvas.size != self.app.canvas_size:  # another display than the canvas was made for
            self.canvas = PixelCanvas(self.app.canvas_size)
            self._widget.canvas = self.canvas
            self._widget.cursor = (self.canvas.size // 2, self.canvas.size // 2)
            self._widget.reset()
            self.query_one("#canvas-box").border_title = f"Canvas {self.canvas.size}x{self.canvas.size}"
        self._diy_active = False
        self._fit()
        self._update_palette()
        self._update()

    def on_screen_suspend(self) -> None:
        self.save_canvas()

    def save_canvas(self) -> None:
        if self.canvas is None:
            return
        try:
            self.canvas_file.parent.mkdir(parents=True, exist_ok=True)
            self.canvas.to_image().save(self.canvas_file)
        except OSError:
            logging.exception("could not save the canvas")

    def on_resize(self) -> None:
        self._fit()

    def _fit(self) -> None:
        if self._widget is None:
            return
        try:
            box = self.query_one("#canvas-box")
        except NoMatches:
            return
        size = self.canvas.size
        self._widget.set_wide(box.size.width - 2 >= size * 2 and box.size.height - 2 >= size)

    # drawing

    def _changed(self) -> None:
        self._widget.update_rows()
        self._update_soon()
        if self.live and self._wake is not None:
            self._wake.set()

    def _update_soon(self) -> None:
        """Updates the texts at the side once for a burst of changes, not for every pixel of a stroke."""
        if self._state_timer is None:
            self._state_timer = self.set_timer(STATE_DELAY_SECONDS, self._update_now)

    def _update_now(self) -> None:
        self._state_timer = None
        self._update()

    def _update_palette(self) -> None:
        palette = Text()
        for index, value in enumerate(PALETTE):
            color = parse_color_rgb(value)
            label = str((index + 1) % 10) if index < 10 else " "
            selected = color == self.color
            palette.append(f" {label} ", Style(color=style_of(contrast(color)), bgcolor=style_of(color),
                                              bold=selected, underline=selected))
            if index % Palette.PER_ROW == Palette.PER_ROW - 1:
                palette.append("\n")
        self.query_one("#palette", Static).update(palette)

    def _update(self) -> None:
        if self._widget is None:
            return
        x, y = self._widget.cursor
        state = Text()
        state.append("Color  ")
        state.append("   ", Style(bgcolor=style_of(self.color)))
        state.append(f" {hex_of(self.color)}\n")
        state.append(f"Cursor {x},{y}  now {hex_of(self.canvas.get(x, y))}\n")
        state.append("Pen    " + ("down, moving paints" if self.pen_down else "up") + "\n")
        state.append("Live   " + ("on, every change is sent" if self.live else "off, S sends") + "\n")
        if self.tool:
            state.append(f"{self.tool.capitalize()} from the yellow pixel: move, then press {self.tool[0].upper()}\n",
                         style="bold yellow")
        if not self._widget.wide:
            state.append("Mouse: left paints the upper pixel, Shift the lower, right erases, middle picks\n",
                         style="dim")
        self.query_one("#state", Static).update(state)

    def _paint(self, x: int, y: int, color: Color | None = None) -> None:
        self.canvas.set(x, y, self.color if color is None else color)

    def action_move(self, dx: int, dy: int) -> None:
        x, y = self._widget.cursor
        size = self.canvas.size
        self._widget.cursor = (min(max(x + dx, 0), size - 1), min(max(y + dy, 0), size - 1))
        if self.pen_down:
            self._paint(*self._widget.cursor)
        self._changed()

    def action_paint(self) -> None:
        self.canvas.begin()
        self._paint(*self._widget.cursor)
        self._changed()

    def action_pen(self) -> None:
        """Puts the pen down (moving paints, one undo step for the whole stroke) or lifts it."""
        self.pen_down = not self.pen_down
        if self.pen_down:
            self.canvas.begin()
            self._paint(*self._widget.cursor)
        self._changed()

    def action_erase(self) -> None:
        self.canvas.begin()
        self._paint(*self._widget.cursor, color=BLACK)
        self._changed()

    def action_fill(self) -> None:
        self.canvas.begin()
        self.canvas.fill(*self._widget.cursor, self.color)
        self._changed()

    def action_line(self) -> None:
        self._two_corners("line", self.canvas.line)

    def action_box(self) -> None:
        self._two_corners("box", self.canvas.rectangle)

    def _two_corners(self, tool: str, draw) -> None:
        if self.tool != tool or self._widget.anchor is None:
            self.tool = tool
            self._widget.anchor = self._widget.cursor
        else:
            self.canvas.begin()
            draw(*self._widget.anchor, *self._widget.cursor, self.color)
            self.action_cancel()
            return
        self._changed()

    def action_cancel(self) -> None:
        self.tool = None
        self._widget.anchor = None
        self._changed()

    def action_pick(self) -> None:
        self._use_color(self.canvas.get(*self._widget.cursor))

    def _use_color(self, color: Color) -> None:
        self.color = color
        self.app.session.draw_color = hex_of(color)
        self.app.session.save(self.app.session_path)
        self._update_palette()
        self._update()

    def action_palette(self, index: int) -> None:
        if 0 <= index < len(PALETTE):
            self._use_color(parse_color_rgb(PALETTE[index]))

    def action_palette_step(self, step: int) -> None:
        colors = [parse_color_rgb(value) for value in PALETTE]
        index = colors.index(self.color) if self.color in colors else -1
        self._use_color(colors[(index + step) % len(colors)])

    def action_color(self) -> None:
        def chosen(text: str | None) -> None:
            if text is None:
                return
            try:
                self._use_color(parse_color_rgb(text))
            except (ValueError, TypeError):
                self.app.show_message(f"{text!r} is not a color", "error")

        self.app.push_screen(TextDialog("Color", "#rrggbb or a name", hex_of(self.color)), chosen)

    def action_undo(self) -> None:
        if self.canvas.undo():
            self._changed()

    def action_redo(self) -> None:
        if self.canvas.redo():
            self._changed()

    def action_clear(self) -> None:
        self.canvas.begin()
        self.canvas.clear()
        self._changed()

    def action_live(self) -> None:
        self.live = not self.live
        self._update()
        if self.live and self._wake is not None:
            self._wake.set()

    # the mouse

    def _pointer(self, x: int, y: int, button: int, started: bool) -> None:
        if not self.canvas.inside(x, y):
            return
        self._widget.cursor = (x, y)
        if button == 2:
            self._use_color(self.canvas.get(x, y))
        else:
            if started:
                self.canvas.begin()
            self._paint(x, y, BLACK if button == 3 else None)
        self._changed()

    # files

    def action_open(self) -> None:
        def chosen(path: Path | None) -> None:
            if path is None:
                return
            try:
                with PILImage.open(path) as image:
                    self.canvas.begin()
                    self.canvas.load(image)
            except (OSError, ValueError) as e:
                self.app.show_message(f"Cannot open {path.name}: {e}", "error")
                return
            self._changed()

        self.app.push_screen(
            PathDialog(self.app.folder, "Open a picture", "Path of a picture, it is scaled to the canvas"), chosen)

    def action_save(self) -> None:
        def chosen(text: str | None) -> None:
            if text is None:
                return
            path = Path(text).expanduser()
            path = path if path.suffix else path.with_suffix(".png")
            try:
                self.canvas.to_image().save(path)
            except (OSError, ValueError) as e:
                self.app.show_message(f"Cannot save {path.name}: {e}", "error")
                return
            self.app.show_message(f"Saved {path}")

        self.app.push_screen(
            TextDialog("Save", "File to save the drawing in (PNG)", str(self.app.folder / "drawing.png")), chosen)

    # the display

    def action_send(self) -> None:
        """Sends the changes, or everything if the display was not in the draw mode yet."""
        if self._wake is not None:
            self._wake.set()

    def action_show(self) -> None:
        """Shows the drawing as a picture, which leaves the draw mode."""
        colors = self.canvas.colors()
        self.app.run_device("Showing the drawing", lambda: self.app.client.image.show_image_pixeldata(colors))

    async def _sender(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            await asyncio.sleep(0.05)  # a stroke changes many pixels, send them together
            try:
                await self._send()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.exception("could not send the drawing")
                self.app.show_message(f"Drawing failed: {e}", "error")

    async def _send(self) -> None:
        app = self.app
        if app.client is None or app.connection != "connected":
            return
        if app.busy:  # an upload is running, the pixels wait
            await asyncio.sleep(0.3)
            self._wake.set()
            return
        everything = not self._diy_active or self._generation != app.device_generation
        if everything:
            await app.client.image.set_mode(ImageMode.EnableDIY)
            self._diy_active = True
            self._generation = app.device_generation
            pixels = self.canvas.everything()
        else:
            pixels = self.canvas.take_dirty()
        by_color: dict[Color, list[tuple[int, int]]] = {}
        for xy, color in pixels.items():
            by_color.setdefault(color, []).append(xy)
        # the black that clears the rest of the display goes last, what was drawn shows first
        for color, xys in sorted(by_color.items(), key=lambda item: item[0] == BLACK):
            iterator = iter(xys)
            while chunk := list(islice(iterator, MAX_PIXEL_LIST_LENGTH)):
                await app.client.graffiti.set_pixels(color, chunk)
