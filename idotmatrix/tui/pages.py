from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

from idotmatrix.tui.devicebar import DeviceBar

# the pages of the app: id, title, key
PAGES = (
    ("files", "Files", "f1"),
    ("controls", "Controls", "f2"),
    ("draw", "Draw", "f3"),
)


class Tab(Static):
    """A page in the status bar: a click shows it."""

    ALLOW_SELECT = False
    DEFAULT_CSS = "Tab { width: auto; padding: 0 1; } Tab:hover { background: $boost; }"

    def __init__(self, page_id: str, title: str, key: str, active: bool):
        text = Text(f"{key.upper()} {title}", style="bold reverse" if active else "dim")
        super().__init__(text, id=f"tab-{page_id}")
        self.page_id = page_id

    def on_click(self) -> None:
        self.app.action_page(self.page_id)


class StatusBar(Horizontal):
    """The line at the top of every page: the pages, the connection to the display and the latest message."""

    DEFAULT_CSS = """
    StatusBar { height: 1; background: $panel; color: $text; }
    StatusBar > #status { width: auto; padding: 0 1; }
    StatusBar > #message { width: 1fr; padding: 0 1; text-align: right; text-wrap: nowrap; text-overflow: ellipsis; }
    """

    def __init__(self, active: str):
        super().__init__()
        self._active = active

    def compose(self) -> ComposeResult:
        for page_id, title, key in PAGES:
            yield Tab(page_id, title, key, page_id == self._active)
        yield Static("", id="status")
        yield Static("", id="message")

    def on_mount(self) -> None:
        self.show(self.app.status_text, self.app.message_text)

    def show(self, status: Text, message: Text) -> None:
        self.query_one("#status", Static).update(status)
        self.query_one("#message", Static).update(message)


class PageScreen(Screen):
    """A page of the app: the status bar, the content and the footer with the keys."""

    page_id = ""

    def compose(self) -> ComposeResult:
        yield StatusBar(self.page_id)
        yield from self.content()
        yield DeviceBar()
        yield Footer()

    def content(self) -> ComposeResult:
        return iter(())
