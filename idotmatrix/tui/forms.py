import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static

from idotmatrix.tui.widgets import (ChoiceField, ColorField, ColorListField, ErrorLabel, Field as FieldWidget,
                                    FieldChanged, NumberField, TextField, Toggle, try_color)

logging = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})$")
DURATION_PATTERN = re.compile(r"^(\d{1,2})(?::(\d{1,2}))?$")


@dataclass(frozen=True)
class Field:
    """One input of a feature. `kind` is choice, bool, int, text, color, colors, time or duration."""
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
    icon: str = ""


@dataclass(frozen=True)
class Feature:
    """
    A feature of the display with the inputs and buttons that control it. `live`: the first button runs on every
    change. `preview` is "text" or "effect". `form` replaces the whole form with a widget of its own.
    """
    id: str
    title: str
    help: str
    fields: tuple = ()
    actions: tuple = ()
    live: bool = False
    preview: str = ""
    form: Callable | None = None

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
            elif item.kind == "int" and isinstance(value, (int, str)) and not isinstance(value, bool):
                values[item.key] = str(value)
            elif item.kind in ("text", "color", "time", "duration") and isinstance(value, str):
                values[item.key] = value
            elif item.kind == "colors" and isinstance(value, list) and all(isinstance(part, str) for part in value):
                values[item.key] = value
        return values

    def check(self, raw: dict) -> dict:
        """The values for the actions. Raises ValueError with a message for the user if one is not valid."""
        return {item.key: check_field(item, raw.get(item.key, item.default)) for item in self.fields}


def check_field(item: Field, value):
    """The value of a field for the actions. Raises ValueError that says what is wrong and how to enter it."""
    if item.kind in ("choice", "bool"):
        return value
    if item.kind == "colors":
        colors = []
        for part in value:
            color = try_color(part)
            if color is None:
                raise ValueError(f"{part!r} is not a color: use #rrggbb or an HTML color name like tomato")
            colors.append(color)
        return colors
    text = str(value).strip()
    if item.kind == "int":
        try:
            number = int(text)
        except ValueError:
            raise ValueError(f"Enter a whole number from {item.low} to {item.high}") from None
        if not item.low <= number <= item.high:
            raise ValueError(f"Enter a number from {item.low} to {item.high}")
        return number
    if not text:
        if item.required:
            raise ValueError("Enter something")
        return None
    if item.kind == "text":
        return str(value)
    if item.kind == "color":
        color = try_color(text)
        if color is None:
            raise ValueError(f"{text!r} is not a color: use #rrggbb or an HTML color name like tomato")
        return color
    if item.kind == "time":
        match = TIME_PATTERN.match(text)
        if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
            raise ValueError("Use hours and minutes like 22:30 (00:00 to 23:59)")
        return int(match.group(1)), int(match.group(2))
    if item.kind == "duration":
        match = DURATION_PATTERN.match(text)
        minutes, seconds = (int(match.group(1)), int(match.group(2) or 0)) if match else (-1, -1)
        if not match or minutes > 59 or seconds > 59 or (match.group(2) is not None and len(match.group(2)) != 2):
            raise ValueError("Use minutes:seconds like 12:34, up to 59:59 (a single number is minutes)")
        return minutes, seconds
    raise ValueError(f"unknown kind {item.kind}")


class FeatureForm(VerticalScroll, can_focus=False):
    """
    The inputs and buttons of a feature. Up and Down go from one to the next, Left and Right change a value, Enter
    (or Ctrl+J) applies the settings, buttons are used with Enter or a click.
    """

    DEFAULT_CSS = """
    FeatureForm { padding: 0 1; }
    FeatureForm .title { text-style: bold; color: $primary; }
    FeatureForm .help { color: $text-muted; margin-bottom: 1; }
    FeatureForm .row { height: 1; margin-top: 1; }
    FeatureForm .row Label { width: 28; color: $text-muted; }
    FeatureForm .row Field, FeatureForm .row ColorField, FeatureForm .row TextField { width: 1fr; }
    FeatureForm .buttons { height: auto; margin-top: 2; }
    FeatureForm Button { margin-right: 2; }
    """
    BINDINGS = [
        Binding("up", "field(-1)", show=False),
        Binding("down", "field(1)", show=False),
        Binding("left", "button(-1)", show=False),
        Binding("right", "button(1)", show=False),
        Binding("enter", "apply", "Apply"),
        Binding("ctrl+j,ctrl+enter", "apply", "Apply", show=False),
    ]

    def __init__(self, feature: Feature, values: dict, **kwargs):
        super().__init__(**kwargs)
        self.feature = feature
        self._values = values
        self._armed = False
        self._live_timer = None
        self._widgets: dict[str, Widget] = {}
        self._errors: dict[str, ErrorLabel] = {}
        self.preview = None

    def compose(self) -> ComposeResult:
        yield Label(self.feature.title, classes="title")
        yield Static(self.feature.help, classes="help")
        for item in self.feature.fields:
            widget = self._make(item, self._values[item.key])
            self._widgets[item.key] = widget
            with Horizontal(classes="row"):
                yield Label(item.label)
                yield widget
            error = ErrorLabel()
            self._errors[item.key] = error
            yield error
        if self.feature.preview:
            from idotmatrix.tui.previews import EffectPreview, TextPreview
            self.preview = EffectPreview() if self.feature.preview == "effect" else TextPreview()
            yield self.preview
        with Horizontal(classes="buttons"):
            for index, action in enumerate(self.feature.actions):
                label = f"{action.icon} {action.label}" if action.icon else action.label
                yield Button(label, id=f"{self.feature.id}-action{index}", variant=action.variant, compact=True)

    def _make(self, item: Field, value) -> Widget:
        if item.kind == "choice":
            return ChoiceField(item.key, item.choices, value, title=item.label)
        if item.kind == "bool":
            return Toggle(item.key, value)
        if item.kind == "int":
            return NumberField(item.key, int(value) if str(value).lstrip("-").isdigit() else item.low, item.low,
                               item.high)
        if item.kind == "color":
            return ColorField(item.key, value, item.placeholder, item.required)
        if item.kind == "colors":
            return ColorListField(item.key, value)
        return TextField(item.key, value, item.placeholder)

    def on_mount(self) -> None:
        # the widgets report their initial value as a change
        self.call_after_refresh(self._arm)

    def _arm(self) -> None:
        self._armed = True
        self._refresh_preview()

    def raw(self) -> dict:
        return {key: widget.raw for key, widget in self._widgets.items()}

    # moving

    def _targets(self) -> list[Widget]:
        targets = [widget.focus_target() for widget in self._widgets.values()]
        return targets + list(self.query(Button))

    def focus_first(self) -> None:
        targets = self._targets()
        if targets:
            targets[0].focus()

    def action_field(self, delta: int) -> None:
        targets = self._targets()
        focused = self.app.focused
        if focused not in targets:
            return
        index = targets.index(focused) + delta
        if 0 <= index < len(targets):
            targets[index].focus()
            self.scroll_to_widget(targets[index])

    def check_action(self, action: str, parameters: tuple) -> bool | None:
        if action == "button":
            return isinstance(self.app.focused, Button)
        if action == "apply":
            return not isinstance(self.app.focused, Button)
        return True

    def action_button(self, delta: int) -> None:
        buttons = list(self.query(Button))
        focused = self.app.focused
        if focused in buttons:
            index = buttons.index(focused) + delta
            if 0 <= index < len(buttons):
                buttons[index].focus()

    # changes

    @on(FieldChanged)
    def _field_changed(self, event: FieldChanged) -> None:
        event.stop()
        if not self._armed:
            return
        valid = self._validate()
        if not valid:
            return
        self._refresh_preview()
        self._live()

    def _validate(self) -> bool:
        """Shows what is wrong under the fields, returns whether every field is valid."""
        raw = self.raw()
        valid = True
        for item in self.feature.fields:
            try:
                check_field(item, raw[item.key])
                self._errors[item.key].show("")
            except ValueError as e:
                self._errors[item.key].show(str(e))
                valid = False
        return valid

    def _refresh_preview(self) -> None:
        if self.preview is None:
            return
        try:
            self.preview.show(self.feature.check(self.raw()))
        except ValueError:
            pass

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_apply()

    def _live(self) -> None:
        if not (self.feature.live and self.feature.actions):
            return
        # a value that is changed several times in a row sends the last one only
        if self._live_timer is not None:
            self._live_timer.stop()
        self._live_timer = self.set_timer(0.25, lambda: self.run_action(self.feature.actions[0], quick=True))

    # running

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        event.stop()
        index = int(str(event.button.id).rsplit("action", 1)[1])
        self.run_action(self.feature.actions[index])

    def action_apply(self) -> None:
        """Runs the first button."""
        if self.feature.actions:
            self.run_action(self.feature.actions[0])

    def run_action(self, action: Action, quick: bool = False) -> None:
        app = self.app
        try:
            raw = self.raw()
        except NoMatches:
            return
        if not self._validate():
            app.show_message("Some values are not valid, see the red texts", "error")
            return
        values = self.feature.check(raw)
        app.session.controls[self.feature.id] = raw
        app.session.save(app.session_path)

        def run() -> None:
            if quick:
                app.quick(self.feature.id, lambda: self._run(action, values))
            else:
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


__all__ = ["Action", "Feature", "FeatureForm", "Field", "FieldWidget", "check_field"]
