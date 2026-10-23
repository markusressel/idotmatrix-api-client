import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, SelectionList, Select
from textual.widgets.selection_list import Selection

from idotmatrix.tui.settings import COLOR_CHOICES, RESIZE_CHOICES, Options
from idotmatrix.util.device_material import MAX_DISPLAY_TIME_SECONDS, SLOTS
from idotmatrix.util.overlay import POSITIONS


class Dialog(ModalScreen):
    """A dialog with a title, content and the buttons OK and Cancel. Escape cancels."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    DEFAULT_CSS = """
    Dialog { align: center middle; background: $background 60%; }
    Dialog > Vertical {
        width: 64; height: auto; max-height: 90%; padding: 1 2;
        border: round $primary; border-title-color: $primary; border-title-style: bold; background: $surface;
    }
    Dialog .field { margin-top: 1; color: $text-muted; }
    Dialog .error { color: $error; height: auto; }
    Dialog Horizontal { height: auto; margin-top: 1; align-horizontal: right; }
    Dialog Button { margin-left: 2; min-width: 12; }
    Dialog Input, Dialog Select { background: $boost; }
    """

    title_text = ""

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = self.title_text
            yield from self.fields()
            yield Label("", id="error", classes="error")
            with Horizontal():
                yield Button("Cancel", id="cancel")
                yield Button("OK", id="ok", variant="primary")

    def fields(self) -> ComposeResult:
        return iter(())

    def result(self):
        """The value of the dialog. Raises ValueError (with a message for the user) if the input is not valid."""
        return True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.accept()
        else:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.accept()

    def accept(self) -> None:
        try:
            value = self.result()
        except ValueError as e:
            self.query_one("#error", Label).update(str(e))
            return
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class OptionsDialog(Dialog):
    title_text = "Options"

    def __init__(self, options: Options):
        super().__init__()
        self._options = options

    def fields(self) -> ComposeResult:
        o = self._options
        yield Label("Colors (auto picks what still looks fine)", classes="field")
        yield Select([(c, c) for c in COLOR_CHOICES], value=o.colors, allow_blank=False, compact=True, id="colors")
        yield Label("Largest GIF in KB (empty: no limit, drops frames first)", classes="field")
        yield Input(str(o.max_size_kb or ""), id="max_size", type="integer", placeholder="no limit", compact=True)
        yield Label("Scale", classes="field")
        yield Select([(c, c) for c in RESIZE_CHOICES], value=o.resize_mode, allow_blank=False, compact=True, id="resize")
        yield Label("Label", classes="field")
        yield Select([("none", "none"), ("file name", "name"), ("text", "text")], value=o.label,
                     allow_blank=False, compact=True, id="label")
        yield Input(o.label_text, id="label_text", placeholder="text of the label", compact=True)
        yield Select([(p, p) for p in POSITIONS], value=o.label_position, allow_blank=False, compact=True, id="position")

    def result(self) -> Options:
        max_size = self.query_one("#max_size", Input).value.strip()
        if max_size and int(max_size) < 1:
            raise ValueError("The largest GIF has to be at least 1 KB")
        label = self.query_one("#label", Select).value
        label_text = self.query_one("#label_text", Input).value
        if label == "text" and not label_text:
            raise ValueError("Enter the text of the label")
        return Options(
            colors=self.query_one("#colors", Select).value,
            max_size_kb=int(max_size) if max_size else None,
            resize_mode=self.query_one("#resize", Select).value,
            label=label,
            label_text=label_text,
            label_position=self.query_one("#position", Select).value,
        )


class SlideshowDialog(Dialog):
    title_text = "Store in slots"

    def __init__(self, count: int, slots: list[int], display_time: int):
        super().__init__()
        self._count = count
        self._slots = slots
        self._display_time = display_time
        self.title_text = f"Store {count} file{'s' if count != 1 else ''} in slots"

    def fields(self) -> ComposeResult:
        yield Label("Slots the device may use (the others are not touched)", classes="field")
        yield SelectionList[int](*[Selection(f"slot {slot}", slot, slot in self._slots) for slot in SLOTS], id="slots")
        yield Label("Seconds each item stays on screen", classes="field")
        yield Input(str(self._display_time), id="time", type="integer", compact=True)

    def result(self) -> tuple[list[int], int]:
        slots = sorted(self.query_one("#slots", SelectionList).selected)
        if not slots:
            raise ValueError("Select at least one slot")
        if len(slots) < self._count:
            raise ValueError(f"{self._count} files do not fit into {len(slots)} slots")
        text = self.query_one("#time", Input).value.strip()
        if not text or not 1 <= int(text) <= MAX_DISPLAY_TIME_SECONDS:
            raise ValueError(f"The time has to be between 1 and {MAX_DISPLAY_TIME_SECONDS} seconds")
        return slots, int(text)


class NumberDialog(Dialog):
    def __init__(self, title: str, label: str, value: int, low: int, high: int):
        super().__init__()
        self.title_text = title
        self._label = label
        self._value = value
        self._low = low
        self._high = high

    def fields(self) -> ComposeResult:
        yield Label(self._label, classes="field")
        yield Input(str(self._value), id="number", type="integer", compact=True)

    def result(self) -> int:
        text = self.query_one("#number", Input).value.strip()
        if not text or not self._low <= int(text) <= self._high:
            raise ValueError(f"Enter a number from {self._low} to {self._high}")
        return int(text)


def parse_path(text: str, base: Path) -> Path:
    """A pasted path: quotes, `file://` and `~` are fine, a relative path is relative to `base`."""
    text = text.strip()
    if len(text) > 1 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1].strip()
    if text.startswith("file://"):
        text = unquote(urlparse(text).path)
    if not text:
        raise ValueError("Enter a path")
    path = Path(text).expanduser()
    path = path if path.is_absolute() else base / path
    path = Path(os.path.normpath(path))
    if not path.exists():
        raise ValueError(f"{path} does not exist")
    return path


class PathDialog(Dialog):
    """Asks for a folder, or a file whose folder is opened with the file selected."""

    def __init__(self, folder: Path):
        super().__init__()
        self.title_text = "Go to"
        self._folder = folder

    def fields(self) -> ComposeResult:
        yield Label("Path of a folder or file, paste it here", classes="field")
        yield Input(str(self._folder), id="path", compact=True, select_on_focus=True)

    def result(self) -> Path:
        return parse_path(self.query_one("#path", Input).value, self._folder)


class ConfirmDialog(Dialog):
    def __init__(self, title: str, message: str):
        super().__init__()
        self.title_text = title
        self._message = message

    def fields(self) -> ComposeResult:
        yield Label(self._message, classes="field")
