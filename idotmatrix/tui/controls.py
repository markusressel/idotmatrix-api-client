from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import ContentSwitcher, OptionList
from textual.widgets.option_list import Option

from idotmatrix.tui.features import FEATURES
from idotmatrix.tui.forms import FeatureForm
from idotmatrix.tui.pages import PageScreen


class ControlsScreen(PageScreen):
    """The features of the display, one form each: clock, text, colors, effects, timers and so on."""

    page_id = "controls"
    BINDINGS = [
        Binding("right", "to_form", "Edit"),
        Binding("escape", "to_list", "List"),
    ]
    DEFAULT_CSS = """
    ControlsScreen #controls { height: 1fr; padding: 0 1; }
    ControlsScreen #features { width: 26; height: 1fr; border: round $primary; border-title-color: $primary; padding: 0 1;
                               background: transparent; }
    ControlsScreen #features:focus { border: round $accent; }
    ControlsScreen #forms { width: 1fr; border: round $primary-darken-1; border-title-color: $primary;
                            padding: 1 1; margin-left: 1; }
    ControlsScreen #forms:focus-within { border: round $accent; }
    """

    def content(self) -> ComposeResult:
        with Horizontal(id="controls"):
            features = OptionList(*[Option(feature.title, id=feature.id) for feature in FEATURES], id="features")
            features.border_title = "Features"
            yield features
            with ContentSwitcher(initial=FEATURES[0].id, id="forms") as forms:
                forms.border_title = "Controls"
                for feature in FEATURES:
                    saved = self.app.session.controls.get(feature.id)
                    values = feature.restore(saved)
                    yield (feature.form or FeatureForm)(feature, values, id=feature.id)

    def on_mount(self) -> None:
        features = self.query_one("#features", OptionList)
        features.highlighted = 0
        features.focus()

    @on(OptionList.OptionHighlighted)
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.query_one("#forms", ContentSwitcher).current = event.option.id

    @on(OptionList.OptionSelected)
    def _selected(self) -> None:
        self.action_to_form()

    def action_to_form(self) -> None:
        if self.query_one("#features", OptionList).has_focus:
            self.query_one("#forms", ContentSwitcher).visible_content.focus_first()

    def action_to_list(self) -> None:
        self.query_one("#features", OptionList).focus()
