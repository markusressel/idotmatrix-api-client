"""Inputs for the forms: made for the keyboard first (arrows change a value, Enter applies it), the mouse works as well."""
import colorsys
from collections.abc import Callable

from PIL import ImageColor
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widget import Widget
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from idotmatrix.util.color_utils import parse_color_rgb

COLOR_NAMES = sorted(name for name in ImageColor.colormap if not name.startswith("#"))
ON_COLOR = "bold green"
OFF_COLOR = "dim"


def try_color(text: str) -> tuple[int, int, int] | None:
    """The color of a hex code or an HTML color name, or None if it is neither."""
    try:
        return parse_color_rgb(text.strip()) if text.strip() else None
    except (ValueError, TypeError):
        return None


def hex_of(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def rainbow(text: str) -> Text:
    """The text with every letter in another color, for the entries of a list that mean rainbow."""
    result = Text()
    for index, letter in enumerate(text):
        red, green, blue = colorsys.hsv_to_rgb(index / max(len(text), 1) * 0.85, 0.8, 1)
        result.append(letter, style=f"rgb({int(red * 255)},{int(green * 255)},{int(blue * 255)})")
    return result


class FieldChanged(Message):
    """A field of a form got another value."""

    def __init__(self, field: Widget):
        super().__init__()
        self.field = field


class Field(Widget):
    """What the fields of a form have in common."""

    can_focus = True
    ALLOW_SELECT = False
    DEFAULT_CSS = """
    Field { height: 1; background: transparent; }
    Field:focus { background: $accent 50%; }
    """

    def __init__(self, key: str, **kwargs):
        super().__init__(**kwargs)
        self.key = key

    @property
    def raw(self):
        raise NotImplementedError

    def focus_target(self) -> Widget:
        return self

    def changed(self) -> None:
        self.refresh()
        self.post_message(FieldChanged(self))


class Toggle(Field):
    """On or off: Space, Left, Right or a click switch it."""

    BINDINGS = [
        Binding("space", "toggle", show=False),
        Binding("left,right", "toggle", show=False),
    ]

    def __init__(self, key: str, value: bool, **kwargs):
        super().__init__(key, **kwargs)
        self.value = value

    @property
    def raw(self) -> bool:
        return self.value

    def render(self) -> Text:
        if self.value:
            return Text.assemble(("● ", ON_COLOR), ("on", ON_COLOR))
        return Text.assemble(("○ ", OFF_COLOR), ("off", OFF_COLOR))

    def action_toggle(self) -> None:
        self.value = not self.value
        self.changed()

    def on_click(self) -> None:
        self.focus()
        self.action_toggle()


class NumberField(Field):
    """A whole number: Left and Right (or - and +) change it by one, Shift and Page keys by ten, digits type it."""

    BINDINGS = [
        Binding("left,minus", "step(-1)", show=False),
        Binding("right,plus,equals_sign", "step(1)", show=False),
        Binding("shift+left,pagedown", "step(-10)", show=False),
        Binding("shift+right,pageup", "step(10)", show=False),
        Binding("shift+up", "step(1)", show=False),
        Binding("shift+down", "step(-1)", show=False),
        Binding("backspace", "erase", show=False),
    ]

    def __init__(self, key: str, value: int, low: int, high: int, **kwargs):
        super().__init__(key, **kwargs)
        self.text = str(value)
        self.low = low
        self.high = high
        self._fresh = True

    @property
    def raw(self) -> str:
        return self.text

    def number(self) -> int | None:
        try:
            return int(self.text)
        except ValueError:
            return None

    def render(self) -> Text:
        shown = self.text or " "
        text = Text.assemble(("‹ ", "bold"), (shown, "bold"), (" ›", "bold"))
        text.append(f"   {self.low} to {self.high}", style="dim")
        return text

    def action_step(self, delta: int) -> None:
        current = self.number()
        if current is None:
            current = self.low
        self.text = str(min(max(current + delta, self.low), self.high))
        self._fresh = True
        self.changed()

    def action_erase(self) -> None:
        self.text = self.text[:-1]
        self._fresh = False
        self.changed()

    def on_blur(self) -> None:
        self._fresh = True

    def on_key(self, event: events.Key) -> None:
        if event.character and event.character.isdigit():
            self.text = event.character if self._fresh else self.text + event.character
            self.text = self.text[:len(str(self.high)) + 1]
            self._fresh = False
            event.stop()
            self.changed()

    def on_click(self, event: events.Click) -> None:
        self.focus()
        if event.x < 3:
            self.action_step(-1)
        elif event.x < len(self.text) + 5:
            self.action_step(1) if event.x >= len(self.text) + 3 else None

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.action_step(1)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.action_step(-1)


class ChoiceDialog(ModalScreen):
    """Pick one of a list of choices, with the keys or the mouse."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    ChoiceDialog { align: center middle; background: $background 60%; }
    ChoiceDialog OptionList { width: 44; max-height: 90%; height: auto; border: round $primary;
                              border-title-color: $primary; background: $surface; }
    """

    def __init__(self, title: str, choices: list, index: int):
        super().__init__()
        self._title = title
        self._choices = choices
        self._index = index

    def compose(self) -> ComposeResult:
        options = OptionList(*[Option(label) for label, _ in self._choices])
        options.border_title = self._title
        yield options

    def on_mount(self) -> None:
        options = self.query_one(OptionList)
        options.highlighted = self._index
        options.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ChoiceField(Field):
    """One of a list: Left and Right go through it, Space or a click opens the whole list."""

    BINDINGS = [
        Binding("left", "step(-1)", show=False),
        Binding("right", "step(1)", show=False),
        Binding("space", "open", show=False),
    ]

    def __init__(self, key: str, choices: tuple, value, title: str = "", **kwargs):
        super().__init__(key, **kwargs)
        self.choices = list(choices)
        self.title = title
        values = [choice for _, choice in self.choices]
        self.index = values.index(value) if value in values else 0

    @property
    def raw(self):
        return self.choices[self.index][1]

    def render(self) -> Text:
        label = self.choices[self.index][0]
        label = label if isinstance(label, Text) else Text(label)
        return Text.assemble(("‹ ", "bold"), label, (" ›", "bold"),
                             (f"   {self.index + 1}/{len(self.choices)}", "dim"))

    def action_step(self, delta: int) -> None:
        self.index = (self.index + delta) % len(self.choices)
        self.changed()

    def action_open(self) -> None:
        def chosen(index: int | None) -> None:
            if index is not None:
                self.index = index
                self.changed()

        self.app.push_screen(ChoiceDialog(self.title, self.choices, self.index), chosen)

    def on_click(self) -> None:
        self.focus()
        self.action_open()


class TextField(Field, can_focus=False):
    """A line of text. Typing edits it, Up and Down go to the next field, Enter applies."""

    DEFAULT_CSS = """
    TextField { height: 1; }
    TextField Input { background: transparent; padding: 0; }
    TextField Input:focus { background: $boost; }
    """

    def __init__(self, key: str, value: str, placeholder: str = "", **kwargs):
        super().__init__(key, **kwargs)
        self._value = value
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        yield Input(self._value, placeholder=self._placeholder, compact=True)

    @property
    def raw(self) -> str:
        return self.query_one(Input).value

    def focus_target(self) -> Widget:
        return self.query_one(Input)

    def focus(self, scroll_visible: bool = True):
        self.query_one(Input).focus(scroll_visible)
        return self

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.post_message(FieldChanged(self))


class PlainStatic(Static):
    """Text that cannot be selected, f.e. next to a slider that is dragged."""

    ALLOW_SELECT = False


class Swatch(PlainStatic):
    """A color as a circle, like the one of the connection."""

    DEFAULT_CSS = "Swatch { width: 3; height: 1; padding: 0 1 0 0; }"

    def show(self, color: tuple[int, int, int] | None) -> None:
        if color is None:
            self.update(Text("○", style="dim red"))
        else:
            self.update(Text("●", style="rgb({},{},{})".format(*color)))


class ColorField(Field, can_focus=False):
    """A color: type a hex code or any HTML color name, or open the color wheel (Ctrl+K, F4 or a click on the circle)."""

    DEFAULT_CSS = """
    ColorField { height: 1; layout: horizontal; }
    ColorField Input { width: 1fr; background: transparent; padding: 0; }
    ColorField Input:focus { background: $boost; }
    """
    BINDINGS = [Binding("ctrl+k,f4", "wheel", "Color wheel")]

    def __init__(self, key: str, value: str, placeholder: str = "", required: bool = True, **kwargs):
        super().__init__(key, **kwargs)
        self._value = value
        self._placeholder = placeholder
        self.required = required

    def compose(self) -> ComposeResult:
        yield Swatch()
        yield Input(self._value, placeholder=self._placeholder or "#rrggbb or a name", compact=True,
                    suggester=SuggestFromList(COLOR_NAMES, case_sensitive=False))

    def on_mount(self) -> None:
        self.query_one(Swatch).show(try_color(self._value))

    @property
    def raw(self) -> str:
        return self.query_one(Input).value

    def focus_target(self) -> Widget:
        return self.query_one(Input)

    def focus(self, scroll_visible: bool = True):
        self.query_one(Input).focus(scroll_visible)
        return self

    def set_value(self, value: str) -> None:
        self.query_one(Input).value = value

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.query_one(Swatch).show(try_color(event.value))
        self.post_message(FieldChanged(self))

    def on_click(self, event: events.Click) -> None:
        if event.x < 3:
            self.action_wheel()

    def action_wheel(self) -> None:
        from idotmatrix.tui.colorwheel import ColorDialog

        def chosen(text: str | None) -> None:
            if text:
                self.set_value(text)

        start = try_color(self.raw) or (255, 255, 255)
        self.app.push_screen(ColorDialog(start), chosen)


class ColorListField(Field):
    """A list of colors: Left and Right pick one, Enter or a click opens the color wheel, + adds one, - removes it."""

    BINDINGS = [
        Binding("left", "move(-1)", show=False),
        Binding("right", "move(1)", show=False),
        Binding("space", "wheel", show=False),
        Binding("plus,equals_sign", "add", show=False),
        Binding("minus,delete", "remove", show=False),
    ]

    def __init__(self, key: str, swatches: list[str], low: int = 2, high: int = 7, **kwargs):
        super().__init__(key, **kwargs)
        self.swatches = list(swatches)
        self.low = low
        self.high = high
        self.index = 0

    @property
    def raw(self) -> list[str]:
        return list(self.swatches)

    def render(self) -> Text:
        text = Text()
        for index, value in enumerate(self.swatches):
            color = try_color(value)
            style = "rgb({},{},{})".format(*color) if color else "red"
            selected = index == self.index and self.has_focus
            text.append("[" if selected else " ", "bold")
            text.append("●", style)
            text.append("]" if selected else " ", "bold")
        text.append(f"   + add, - remove, Space picks ({self.low} to {self.high})", style="dim")
        return text

    def action_move(self, delta: int) -> None:
        self.index = min(max(self.index + delta, 0), len(self.swatches) - 1)
        self.refresh()

    def action_add(self) -> None:
        if len(self.swatches) < self.high:
            self.swatches.insert(self.index + 1, self.swatches[self.index])
            self.index += 1
            self.changed()

    def action_remove(self) -> None:
        if len(self.swatches) > self.low:
            del self.swatches[self.index]
            self.index = min(self.index, len(self.swatches) - 1)
            self.changed()

    def action_wheel(self) -> None:
        from idotmatrix.tui.colorwheel import ColorDialog

        def chosen(text: str | None) -> None:
            if text:
                self.swatches[self.index] = text
                self.changed()

        self.app.push_screen(ColorDialog(try_color(self.swatches[self.index]) or (255, 255, 255)), chosen)

    def on_click(self, event: events.Click) -> None:
        self.focus()
        index = event.x // 3
        if index < len(self.swatches):
            self.index = index
            self.action_wheel()

    def on_focus(self) -> None:
        self.refresh()

    def on_blur(self) -> None:
        self.refresh()


class Slider(Widget):
    """A bar to drag or click. Left and Right move it when it has the focus."""

    can_focus = True
    ALLOW_SELECT = False  # dragging moves the slider, it must not select text
    DEFAULT_CSS = "Slider { height: 1; background: transparent; } Slider:focus { background: $boost; }"
    BINDINGS = [
        Binding("left", "step(-1)", show=False),
        Binding("right", "step(1)", show=False),
        Binding("shift+left,pagedown", "step(-10)", show=False),
        Binding("shift+right,pageup", "step(10)", show=False),
    ]
    value = reactive(100)

    class Changed(Message):
        def __init__(self, slider: "Slider", value: int):
            super().__init__()
            self.slider = slider
            self.value = value

    def __init__(self, low: int, high: int, value: int, **kwargs):
        super().__init__(**kwargs)
        self.low = low
        self.high = high
        self.set_reactive(Slider.value, value)
        self._dragging = False

    def render(self) -> Text:
        width = max(self.size.width, 2)
        position = round((self.value - self.low) / (self.high - self.low) * (width - 1))
        text = Text()
        text.append("━" * position, style="green")
        text.append("●", style="bold white")
        text.append("─" * (width - position - 1), style="dim")
        return text

    def _set(self, value: int) -> None:
        value = min(max(value, self.low), self.high)
        if value != self.value:
            self.value = value
            self.post_message(self.Changed(self, value))

    def action_step(self, delta: int) -> None:
        self._set(self.value + delta)

    def _at(self, x: int) -> None:
        width = max(self.size.width - 1, 1)
        self._set(self.low + round(min(max(x, 0), width) / width * (self.high - self.low)))

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self.capture_mouse()
        self._at(event.x)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragging:
            self._at(event.x)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._dragging = False
        self.release_mouse()

    def watch_value(self) -> None:
        self.refresh()


class ErrorLabel(Label):
    """The reason a value is not valid, right under it."""

    DEFAULT_CSS = "ErrorLabel { color: $error; height: auto; display: none; } ErrorLabel.visible { display: block; }"

    def show(self, message: str) -> None:
        self.set_class(bool(message), "visible")
        self.update(message)


def checker(call: Callable[[], None]) -> Callable[[], None]:
    return call
