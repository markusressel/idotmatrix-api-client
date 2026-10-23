from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Label, Static

DIGITS = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" █ ", "██ ", " █ ", " █ ", "███"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
}
MAX_COUNT = 999
SEND_DELAY_SECONDS = 0.15


def big_number(number: int, style: str) -> Text:
    """Three digits in big letters, with the leading zeros dimmed like the unlit segments of a scoreboard."""
    digits = f"{number:03d}"
    text = Text()
    for row in range(5):
        for position, digit in enumerate(digits):
            lit = number >= (100, 10, 1)[position] or position == 2
            text.append("".join(cell * 2 for cell in DIGITS[digit][row]), style=style if lit else "dim " + style.split()[-1])
            text.append("  ")
        if row < 4:
            text.append("\n")
    return text


class Counter(Static):
    """One side of the scoreboard: a click selects it, the arrows and the wheel count, the right button resets it."""

    ALLOW_SELECT = False
    DEFAULT_CSS = """
    Counter { width: 1fr; height: auto; padding: 1 2; border: round $primary-darken-1; text-align: center; }
    Counter.selected { border: round $accent; }
    """

    def __init__(self, index: int, name: str, style: str, **kwargs):
        super().__init__("", **kwargs)
        self.index = index
        self.side = name
        self.style_name = style
        self.count = 0

    def on_mount(self) -> None:
        self.border_title = self.side
        self.refresh_count()

    def refresh_count(self) -> None:
        text = big_number(self.count, self.style_name)
        text.append("\n\n")
        text.append(" ▼ -1 ", style="bold reverse")
        text.append("   ")
        text.append(" ▲ +1 ", style="bold reverse")
        self.update(text)

    def on_click(self, event: events.Click) -> None:
        board = self.parent.parent
        board.select(self.index)
        if event.button == 3:  # the right button resets the counter that was clicked
            board.action_reset()
            return
        # the buttons are in the last line of the counter
        if event.y >= self.size.height - 3:
            middle = self.size.width // 2
            board.change(-1 if event.x < middle else 1)

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        self.parent.parent.select(self.index)
        self.parent.parent.change(1)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        self.parent.parent.select(self.index)
        self.parent.parent.change(-1)


class ScoreboardForm(VerticalScroll, can_focus=True):
    """Two counters shown like a scoreboard. Every change is sent to the display right away."""

    BINDINGS = [
        Binding("left,shift+tab", "select(-1)", "Other side", show=False),
        Binding("right,tab", "select(1)", "Other side", show=False),
        Binding("up,plus,equals_sign", "change(1)", "+1"),
        Binding("down,minus", "change(-1)", "-1"),
        Binding("pageup", "change(10)", "+10", show=False),
        Binding("pagedown", "change(-10)", "-10", show=False),
        Binding("0,delete", "reset", "Reset this side"),
        Binding("r", "reset_both", "Reset both"),
    ]
    DEFAULT_CSS = """
    ScoreboardForm { padding: 0 1; }
    ScoreboardForm .title { text-style: bold; color: $primary; }
    ScoreboardForm .help { color: $text-muted; margin-bottom: 1; }
    ScoreboardForm Horizontal { height: auto; }
    ScoreboardForm Counter { margin-right: 1; }
    """

    def __init__(self, feature, values: dict, **kwargs):
        super().__init__(**kwargs)
        self.feature = feature
        self._values = values
        self._selected = 0
        self._timer = None
        self._counters: list[Counter] = []

    def compose(self) -> ComposeResult:
        yield Label(self.feature.title, classes="title")
        yield Static(self.feature.help, classes="help")
        with Horizontal():
            for index, (name, style) in enumerate((("Home", "bold green"), ("Guest", "bold yellow"))):
                counter = Counter(index, name, style)
                counter.count = int(self._values.get("first" if index == 0 else "second", 0) or 0)
                self._counters.append(counter)
                yield counter

    def on_mount(self) -> None:
        self.select(0)

    def focus_first(self) -> None:
        self.focus()

    def select(self, index: int) -> None:
        self._selected = index % 2
        for counter in self._counters:
            counter.set_class(counter.index == self._selected, "selected")
        self.focus()

    def action_select(self, delta: int) -> None:
        self.select(self._selected + delta)

    def change(self, delta: int) -> None:
        counter = self._counters[self._selected]
        counter.count = min(max(counter.count + delta, 0), MAX_COUNT)
        counter.refresh_count()
        self._send_soon()

    def action_change(self, delta: int) -> None:
        self.change(delta)

    def action_reset(self) -> None:
        self._counters[self._selected].count = 0
        self._counters[self._selected].refresh_count()
        self._send_soon()

    def action_reset_both(self) -> None:
        for counter in self._counters:
            counter.count = 0
            counter.refresh_count()
        self._send_soon()

    def _send_soon(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(SEND_DELAY_SECONDS, self._send)

    def _send(self) -> None:
        first, second = self._counters[0].count, self._counters[1].count
        app = self.app
        app.session.controls[self.feature.id] = {"first": first, "second": second}
        app.session.save(app.session_path)
        app.quick(self.feature.id, lambda: app.client.scoreboard.show(first, second))
