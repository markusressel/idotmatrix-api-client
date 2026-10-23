import colorsys
import math

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Input, Label

from idotmatrix.tui.dialogs import Dialog
from idotmatrix.tui.widgets import COLOR_NAMES, Swatch, hex_of, try_color

Color = tuple[int, int, int]
SIZE = 33  # pixels per side of the wheel, a pixel is a column wide and half a row high
CENTER = (SIZE - 1) / 2
HUE_STEP = 5 / 360
SATURATION_STEP = 0.05
VALUE_STEP = 0.05


def rgb_of(hue: float, saturation: float, value: float) -> Color:
    red, green, blue = colorsys.hsv_to_rgb(hue % 1.0, min(max(saturation, 0), 1), min(max(value, 0), 1))
    return round(red * 255), round(green * 255), round(blue * 255)


def style_of(color: Color) -> str:
    return "rgb({},{},{})".format(*color)


def contrast(color: Color) -> Color:
    return (0, 0, 0) if (color[0] * 299 + color[1] * 587 + color[2] * 114) / 1000 > 128 else (255, 255, 255)


class ColorWheel(Widget):
    """Hue around, saturation from the middle to the edge. Click or drag, or use the arrows."""

    ALLOW_SELECT = False
    can_focus = True
    DEFAULT_CSS = f"ColorWheel {{ width: {SIZE}; height: {(SIZE + 1) // 2}; }}"

    class Picked(Message):
        def __init__(self, hue: float, saturation: float):
            super().__init__()
            self.hue = hue
            self.saturation = saturation

    def __init__(self, hue: float, saturation: float, value: float, **kwargs):
        super().__init__(**kwargs)
        self.hue = hue
        self.saturation = saturation
        self.value = value
        self._dragging = False

    def _marker(self) -> set[tuple[int, int]]:
        x = CENTER + self.saturation * CENTER * math.cos(self.hue * math.tau)
        y = CENTER - self.saturation * CENTER * math.sin(self.hue * math.tau)
        x, y = round(x), round(y)
        return {(x, y), (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)}

    def _pixel(self, x: int, y: int, marker: set[tuple[int, int]]) -> Color | None:
        dx, dy = x - CENTER, y - CENTER
        radius = math.hypot(dx, dy) / CENTER
        if radius > 1.02:
            return None
        color = rgb_of(math.atan2(-dy, dx) / math.tau, radius, self.value)
        return contrast(color) if (x, y) in marker else color

    def render(self) -> Text:
        marker = self._marker()
        text = Text(no_wrap=True, overflow="crop")
        for row in range((SIZE + 1) // 2):
            for x in range(SIZE):
                top, bottom = self._pixel(x, row * 2, marker), self._pixel(x, row * 2 + 1, marker)
                if top is None and bottom is None:
                    text.append(" ")
                elif bottom is None:
                    text.append("▀", Style(color=style_of(top)))
                elif top is None:
                    text.append("▄", Style(color=style_of(bottom)))
                else:
                    text.append("▀", Style(color=style_of(top), bgcolor=style_of(bottom)))
            if row + 1 < (SIZE + 1) // 2:
                text.append("\n")
        return text

    def _pick(self, event: events.MouseEvent) -> None:
        dx, dy = event.x - CENTER, event.y * 2 + 0.5 - CENTER
        self.post_message(self.Picked(math.atan2(-dy, dx) / math.tau % 1.0, min(math.hypot(dx, dy) / CENTER, 1.0)))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self.capture_mouse()
        self.focus()
        self._pick(event)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragging:
            self._pick(event)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._dragging = False
        self.release_mouse()


class ValueBar(Widget):
    """The brightness of the color, dark to light."""

    ALLOW_SELECT = False
    DEFAULT_CSS = f"ValueBar {{ width: {SIZE}; height: 1; }}"

    class Picked(Message):
        def __init__(self, value: float):
            super().__init__()
            self.value = value

    def __init__(self, hue: float, saturation: float, value: float, **kwargs):
        super().__init__(**kwargs)
        self.hue = hue
        self.saturation = saturation
        self.value = value
        self._dragging = False

    def render(self) -> Text:
        position = round(self.value * (SIZE - 1))
        text = Text(no_wrap=True, overflow="crop")
        for x in range(SIZE):
            color = rgb_of(self.hue, self.saturation, x / (SIZE - 1))
            text.append("┃" if x == position else " ",
                        Style(color=style_of(contrast(color)), bgcolor=style_of(color), bold=True))
        return text

    def _pick(self, event: events.MouseEvent) -> None:
        self.post_message(self.Picked(min(max(event.x / (SIZE - 1), 0), 1)))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self.capture_mouse()
        self._pick(event)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragging:
            self._pick(event)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._dragging = False
        self.release_mouse()


class ColorDialog(Dialog):
    """Picks a color on a wheel with the mouse or the arrows, or from a hex code or an HTML color name."""

    title_text = "Color"
    BINDINGS = [
        Binding("left", "hue(-1)", "Hue", show=False),
        Binding("right", "hue(1)", "Hue", show=False),
        Binding("shift+left", "hue(-6)", "Hue", show=False),
        Binding("shift+right", "hue(6)", "Hue", show=False),
        Binding("up", "saturation(1)", "Saturation", show=False),
        Binding("down", "saturation(-1)", "Saturation", show=False),
        Binding("pageup,plus", "value(1)", "Lighter", show=False),
        Binding("pagedown,minus", "value(-1)", "Darker", show=False),
    ]
    DEFAULT_CSS = """
    ColorDialog .wheel { height: auto; align-horizontal: center; margin-top: 1; }
    ColorDialog .input-row { height: 1; margin-top: 1; align-horizontal: left; }
    ColorDialog .input-row Input { width: 1fr; }
    ColorDialog .hint { color: $text-muted; margin-top: 1; height: auto; }
    """

    def __init__(self, color: Color):
        super().__init__()
        self._hue, self._saturation, self._value = colorsys.rgb_to_hsv(*[part / 255 for part in color])
        self._start = color
        self._from_input = False

    def fields(self) -> ComposeResult:
        with Horizontal(classes="wheel"):
            yield ColorWheel(self._hue, self._saturation, self._value, id="wheel")
        with Horizontal(classes="wheel"):
            yield ValueBar(self._hue, self._saturation, self._value, id="bar")
        with Horizontal(classes="input-row"):
            yield Swatch(id="swatch")
            yield Input(hex_of(self._start), id="code", compact=True, placeholder="#rrggbb or a color name",
                        suggester=SuggestFromList(COLOR_NAMES, case_sensitive=False))
        yield Label("Wheel: click, drag or use the arrows.\nLighter and darker: the bar, PgUp and PgDn.\n"
                    "HTML color names work too, Tab completes them.", classes="hint")

    def on_mount(self) -> None:
        self.query_one(ColorWheel).focus()
        self._show()

    def _color(self) -> Color:
        return rgb_of(self._hue, self._saturation, self._value)

    def _show(self) -> None:
        wheel, bar = self.query_one(ColorWheel), self.query_one(ValueBar)
        wheel.hue, wheel.saturation, wheel.value = self._hue, self._saturation, self._value
        bar.hue, bar.saturation, bar.value = self._hue, self._saturation, self._value
        wheel.refresh()
        bar.refresh()
        color = self._color()
        self.query_one(Swatch).show(color)
        if not self._from_input:
            self.query_one("#code", Input).value = hex_of(color)

    def on_color_wheel_picked(self, event: ColorWheel.Picked) -> None:
        self._hue, self._saturation = event.hue, event.saturation
        self._show()

    def on_value_bar_picked(self, event: ValueBar.Picked) -> None:
        self._value = event.value
        self._show()

    def on_input_changed(self, event: Input.Changed) -> None:
        color = try_color(event.value)
        self.query_one(Swatch).show(color)
        if color is not None:
            self._hue, self._saturation, self._value = colorsys.rgb_to_hsv(*[part / 255 for part in color])
            self._from_input = True
            self._show()
            self._from_input = False

    def action_hue(self, steps: int) -> None:
        self._hue = (self._hue + steps * HUE_STEP) % 1.0
        self._show()

    def action_saturation(self, steps: int) -> None:
        self._saturation = min(max(self._saturation + steps * SATURATION_STEP, 0), 1)
        self._show()

    def action_value(self, steps: int) -> None:
        self._value = min(max(self._value + steps * VALUE_STEP, 0), 1)
        self._show()

    def result(self) -> str:
        text = self.query_one("#code", Input).value.strip()
        color = try_color(text)
        if color is None:
            raise ValueError(f"{text!r} is not a color: use #rrggbb or an HTML color name like tomato")
        return hex_of(color)
