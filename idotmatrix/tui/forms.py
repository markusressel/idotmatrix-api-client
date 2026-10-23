import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import Button, Input, Label, Select, Static, Switch

from idotmatrix.util.color_utils import parse_color_rgb

logging = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class Field:
    """One input of a feature. `kind` is choice, bool, int, text, color, colors or time."""
    key: str
    label: str
    kind: str
    default: object
    choices: tuple = ()  # (label, value) of a choice
    low: int = 0
    high: int = 255
    placeholder: str = ""
    required: bool = True


@dataclass(frozen=True)
class Action:
    """A button. `run` gets the client and the checked values, and may return a message to show."""
    label: str
    run: Callable[[object, dict], Awaitable[str | None]]
    variant: str = "default"
    confirm: str = ""  # asks this before it runs


@dataclass(frozen=True)
class Feature:
    """A feature of the display with the inputs and buttons that control it. `live`: the first button runs on change."""
    id: str
    title: str
    help: str
    fields: tuple = ()
    actions: tuple = ()
    live: bool = False

    def defaults(self) -> dict:
        return {item.key: item.default for item in self.fields}

    def restore(self, saved: dict | None) -> dict:
        """The defaults with the saved values that are still valid for the fields."""
        values = self.defaults()
        for item in self.fields:
            value = (saved or {}).get(item.key)
            if item.kind == "choice" and value in [choice for _, choice in item.choices]:
                values[item.key] = value
            elif item.kind == "bool" and isinstance(value, bool):
                values[item.key] = value
            elif item.kind == "int" and isinstance(value, int) and not isinstance(value, bool):
                values[item.key] = value
            elif item.kind in ("text", "color", "colors", "time") and isinstance(value, str):
                values[item.key] = value
        return values

    def check(self, raw: dict) -> dict:
        """The values for the actions. Raises ValueError with a message for the user if one is not valid."""
        return {item.key: _check(item, raw.get(item.key, item.default)) for item in self.fields}


def _check(item: Field, value):
    label = item.label.lower()
    if item.kind in ("choice", "bool"):
        return value
    text = str(value).strip()
    if item.kind == "int":
        try:
            number = int(text)
        except ValueError:
            raise ValueError(f"{item.label}: enter a number") from None
        if not item.low <= number <= item.high:
            raise ValueError(f"{item.label}: enter a number from {item.low} to {item.high}")
        return number
    if not text:
        if item.required:
            raise ValueError(f"{item.label}: enter something")
        return None
    if item.kind == "text":
        return str(value)
    if item.kind == "color":
        try:
            return parse_color_rgb(text)
        except (ValueError, TypeError):
            raise ValueError(f"{item.label}: {text!r} is not a color (#rrggbb or a name)") from None
    if item.kind == "colors":
        parts = [part for part in re.split(r"[,\s]+", text) if part]
        try:
            return [parse_color_rgb(part) for part in parts]
        except (ValueError, TypeError):
            raise ValueError(f"{label}: use colors like #ff0000, separated by commas") from None
    if item.kind == "time":
        match = TIME_PATTERN.match(text)
        if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
            raise ValueError(f"{item.label}: use hours and minutes like 22:30")
        return int(match.group(1)), int(match.group(2))
    raise ValueError(f"unknown kind {item.kind}")


class FeatureForm(VerticalScroll, can_focus=False):
    """The inputs and buttons of a feature."""

    DEFAULT_CSS = """
    FeatureForm { padding: 0 1; }
    FeatureForm .title { text-style: bold; color: $primary; }
    FeatureForm .help { color: $text-muted; margin-bottom: 1; }
    FeatureForm .label { margin-top: 1; color: $text-muted; }
    FeatureForm .switch-row { height: 1; margin-top: 1; }
    FeatureForm .switch-row Label { width: 1fr; color: $text-muted; }
    FeatureForm Switch { border: none; height: 1; padding: 0; width: auto; }
    FeatureForm Input, FeatureForm Select { background: $boost; }
    FeatureForm .buttons { height: auto; margin-top: 2; }
    FeatureForm Button { margin-right: 2; }
    """

    def __init__(self, feature: Feature, values: dict, **kwargs):
        super().__init__(**kwargs)
        self.feature = feature
        self._values = values
        self._armed = False
        self._live_timer = None

    def _wid(self, key: str) -> str:
        return f"{self.feature.id}-{key}"

    def compose(self) -> ComposeResult:
        yield Label(self.feature.title, classes="title")
        yield Static(self.feature.help, classes="help")
        for item in self.feature.fields:
            value = self._values[item.key]
            if item.kind == "choice":
                yield Label(item.label, classes="label")
                yield Select(list(item.choices), value=value, allow_blank=False, compact=True, id=self._wid(item.key))
            elif item.kind == "bool":
                with Horizontal(classes="switch-row"):
                    yield Label(item.label)
                    yield Switch(value, id=self._wid(item.key))
            else:
                yield Label(item.label, classes="label")
                yield Input(str(value), placeholder=item.placeholder, compact=True, id=self._wid(item.key),
                            type="integer" if item.kind == "int" else "text")
        with Horizontal(classes="buttons"):
            for index, action in enumerate(self.feature.actions):
                yield Button(action.label, id=self._wid(f"action{index}"), variant=action.variant, compact=True)

    def on_mount(self) -> None:
        # the widgets report their initial value as a change
        self.call_after_refresh(self._arm)

    def _arm(self) -> None:
        self._armed = True

    def focus_first(self) -> None:
        for widget in self.query("Input, Select, Switch, Button"):
            widget.focus()
            return

    def raw(self) -> dict:
        values = {}
        for item in self.feature.fields:
            widget = self.query_one("#" + self._wid(item.key))
            values[item.key] = widget.value
        return values

    # running

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        event.stop()
        index = int(str(event.button.id).rsplit("action", 1)[1])
        self.run_action(self.feature.actions[index])

    @on(Select.Changed)
    @on(Switch.Changed)
    def _changed(self, event) -> None:
        event.stop()
        self._live()

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self.feature.live:
            self._live(now=True)

    def _live(self, now: bool = False) -> None:
        if not (self.feature.live and self._armed and self.feature.actions):
            return
        # a switch or a list that is changed several times in a row sends the last state only
        if self._live_timer is not None:
            self._live_timer.stop()
        self._live_timer = self.set_timer(0 if now else 0.25, lambda: self.run_action(self.feature.actions[0]))

    def run_action(self, action: Action) -> None:
        app = self.app
        try:
            raw = self.raw()
            values = self.feature.check(raw)
        except ValueError as e:
            app.show_message(str(e), "error")
            return
        except NoMatches:
            return
        app.session.controls[self.feature.id] = raw
        app.session.save(app.session_path)

        def run() -> None:
            app.run_device(action.label, lambda: self._run(action, values))

        if action.confirm:
            from idotmatrix.tui.dialogs import ConfirmDialog

            def confirmed(answer) -> None:
                if answer:
                    run()

            app.push_screen(ConfirmDialog(action.label, action.confirm), confirmed)
        else:
            run()

    async def _run(self, action: Action, values: dict) -> None:
        message = await action.run(self.app.client, values)
        self.app.show_message(message or f"{action.label}: done")
