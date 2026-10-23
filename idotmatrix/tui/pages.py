from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Static

# the pages of the app: id, title, key
PAGES = (
    ("files", "Files", "f1"),
    ("controls", "Controls", "f2"),
    ("draw", "Draw", "f3"),
)


class StatusBar(Horizontal):
    """The line at the top of every page: the pages, the connection to the display and the latest message."""

    DEFAULT_CSS = """
    StatusBar { height: 1; background: $panel; color: $text; }
    StatusBar > #tabs { width: auto; padding: 0 1; }
    StatusBar > #status { width: auto; padding: 0 1; }
    StatusBar > #message { width: 1fr; padding: 0 1; text-align: right; text-wrap: nowrap; text-overflow: ellipsis; }
    """

    def __init__(self, active: str):
        super().__init__()
        self._active = active

    def compose(self) -> ComposeResult:
        yield Static(self._tabs(), id="tabs")
        yield Static("", id="status")
        yield Static("", id="message")

    def on_mount(self) -> None:
        self.show(self.app.status_text, self.app.message_text)

    def _tabs(self) -> Text:
        text = Text()
        for page_id, title, key in PAGES:
            style = "bold reverse" if page_id == self._active else "dim"
            text.append(f" {key.upper()} {title} ", style=style)
            text.append(" ")
        return text

    def show(self, status: Text, message: Text) -> None:
        self.query_one("#status", Static).update(status)
        self.query_one("#message", Static).update(message)


class PageScreen(Screen):
    """A page of the app: the status bar, the content and the footer with the keys."""

    page_id = ""

    def compose(self) -> ComposeResult:
        yield StatusBar(self.page_id)
        yield from self.content()
        yield Footer()

    def content(self) -> ComposeResult:
        return iter(())
