import asyncio
import logging
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.events import Key, Resize
from textual.widgets import DataTable, Footer, Input, Label, ProgressBar, Static
from textual.worker import Worker

from idotmatrix.client import IDotMatrixClient
from idotmatrix.screensize import ScreenSize
from idotmatrix.tui import convert
from idotmatrix.tui.convert import Preview
from idotmatrix.tui.devices import DevicesScreen
from idotmatrix.tui.dialogs import ConfirmDialog, NumberDialog, PathDialog, OptionsDialog, SlideshowDialog
from idotmatrix.tui.files import Entry, files_in, fit_name, format_size, is_supported, list_folder, restore_index
from idotmatrix.tui.preview import PreviewWidget
from idotmatrix.tui.scanner import BleakDeviceScanner, DeviceScanner
from idotmatrix.tui.settings import Options, Session

logging = logging.getLogger(__name__)

NAME_COLUMN_MIN_WIDTH = 8
SIZE_COLUMN_WIDTH = 8
# the width of the cell padding of the three columns, and the mark column
TABLE_FIXED_WIDTH = 1 + 6 + SIZE_COLUMN_WIDTH
DEFAULT_TABLE_WIDTH = 60
MESSAGE_SECONDS = {"information": 5, "warning": 8, "error": 12}
# a key press dismisses the message, but not before it could be read (a held key would dismiss it at once)
MESSAGE_MIN_SECONDS = 1.0
STATUS_COLORS = {"connected": "bold green", "connecting": "bold yellow", "failed": "bold red"}
MESSAGE_STYLES = {"information": "", "warning": "bold yellow", "error": "bold red"}


class FileTable(DataTable):
    """The list of files: ← goes to the parent folder and → into the selected folder, so it never scrolls sideways."""

    BINDINGS = [
        Binding("left", "app.parent", "Up", show=False),
        Binding("right", "app.enter", "Open", show=False),
        Binding("alt+up", "app.parent", "Up", show=False),
        Binding("shift+up", "app.extend(-1)", "Extend marks", show=False),
        Binding("shift+down", "app.extend(1)", "Extend marks", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
    ]

    def action_first(self) -> None:
        self.move_cursor(row=0)

    def action_last(self) -> None:
        self.move_cursor(row=max(self.row_count - 1, 0))

    def action_page(self, direction: int) -> None:
        """Moves the cursor by the rows shown, less one, so the row at the edge stays in view."""
        rows = max(self.scrollable_content_region.height - 1, 1)
        self.move_cursor(row=min(max(self.cursor_row + direction * rows, 0), max(self.row_count - 1, 0)))

    def on_resize(self, event: Resize) -> None:
        self.app.table_resized(event.size.width)
PREVIEW_DELAY_SECONDS = 0.25
DEFAULT_CANVAS_SIZE = 64
CONNECT_ATTEMPTS = 4
CONNECT_RETRY_SECONDS = 1.0


def default_client_factory(address: str | None) -> IDotMatrixClient:
    return IDotMatrixClient(mac_address=address, install_signal_handlers=False)


class IDotMatrixApp(App):
    """Browse a folder, see what a file looks like on the display, and send it."""

    TITLE = "iDotMatrix"
    CSS = """
    Screen { background: $background; }
    #statusbar { height: 1; background: $panel; color: $text; }
    #status { width: auto; padding: 0 1; }
    #message { width: 1fr; padding: 0 1; text-align: right; text-wrap: nowrap; text-overflow: ellipsis; }
    #main { height: 1fr; padding: 0 1; }
    #left { width: 1fr; border: round $primary; border-title-color: $primary; border-title-style: bold;
            border-subtitle-color: $text-muted; padding: 0 1; }
    #right { width: 1fr; }
    #preview-box { height: 1fr; border: round $primary; border-title-color: $primary; border-title-style: bold;
                   padding: 0 1; }
    #info-box { height: auto; max-height: 12; border: round $primary-darken-1; border-title-color: $primary;
                border-title-style: bold; padding: 0 1; }
    #left:focus-within, #preview-box:focus-within { border: round $accent; }
    #filter { display: none; margin-bottom: 1; }
    #filter.visible { display: block; }
    #files { height: 1fr; background: transparent; overflow-x: hidden; }
    #files > .datatable--header { background: transparent; text-style: bold; color: $text-muted; }
    #preview { height: 1fr; min-height: 8; }
    #preview-warning { height: auto; display: none; color: $warning; text-style: bold; text-align: center; }
    #preview-warning.visible { display: block; }
    #info { height: auto; }
    #activity { height: 1; padding: 0 2; }
    #activity Label { width: 1fr; color: $text-muted; }
    #progress { width: 40; }
    """
    BINDINGS = [
        Binding("space", "mark", "Mark"),
        Binding("a", "mark_all", "Mark all"),
        Binding("s", "store", "Slots"),
        Binding("o", "options", "Options"),
        Binding("b", "brightness", "Brightness"),
        Binding("c", "clock", "Clock"),
        Binding("x", "clear_slots", "Clear slots"),
        Binding("d", "devices", "Displays"),
        Binding("r", "reconnect", "Reconnect"),
        Binding("backspace", "parent", "Up", show=False),
        Binding("slash,ctrl+f", "filter", "Filter"),
        Binding("g", "goto", "Go to"),
        Binding("escape", "escape", "Cancel"),
        Binding("colon", "command_palette", "Commands", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        folder: Path | None = None,
        address: str | None = None,
        client_factory: Callable[[str | None], IDotMatrixClient] = default_client_factory,
        session_path: Path | None = None,
        scanner: DeviceScanner | None = None,
        choose_device: bool = False,
    ):
        super().__init__()
        self._scanner = scanner or BleakDeviceScanner()
        self._choose_device = choose_device
        self._device_names: dict[str, str] = {}
        self._session_path = session_path
        self.session = Session.load(session_path)
        if address:
            self.session.address = address
        start = folder or (Path(self.session.folder) if self.session.folder else Path.cwd())
        self.folder = start if start.is_dir() else Path.cwd()
        self._client_factory = client_factory
        self.client: IDotMatrixClient | None = None
        self.connection = "connecting"
        self.canvas_size = DEFAULT_CANVAS_SIZE
        self.marked: list[Path] = []
        self.text_filter = ""
        self._busy: Worker | None = None
        self._preview_timer = None
        self._previewed: Path | None = None
        self._preview: Preview | None = None
        self._loading = False
        self._table_width = 0
        self._message_id = 0
        self._message_shown_at = 0.0

    # layout

    def compose(self) -> ComposeResult:
        with Horizontal(id="statusbar"):
            yield Static("", id="status")
            yield Static("", id="message")
        with Horizontal(id="main"):
            with Vertical(id="left") as left:
                left.border_title = "Files"
                yield Input(placeholder="filter", id="filter")
                yield FileTable(id="files", cursor_type="row")
            with Vertical(id="right"):
                with Vertical(id="preview-box") as box:
                    box.border_title = "On the display"
                    yield PreviewWidget(id="preview")
                    yield Static("", id="preview-warning")
                with Vertical(id="info-box") as info:
                    info.border_title = "Details"
                    yield Static("", id="info")
        with Horizontal(id="activity"):
            yield Label("", id="activity-text")
            yield ProgressBar(id="progress", show_eta=False, total=100)
        yield Footer()

    def on_mount(self) -> None:
        if self.session.theme in self.available_themes:
            self.theme = self.session.theme
        self.theme_changed_signal.subscribe(self, self._theme_changed)
        table = self.query_one("#files", DataTable)
        self.query_one("#progress", ProgressBar).display = False
        self.reload(restore=True)
        self._update_status()
        table.focus()
        if self._choose_device or not self.session.address:
            self.action_devices()
        else:
            self.run_worker(self._connect(), name="connect", exclusive=True, group="connect")

    def _theme_changed(self, theme) -> None:
        self.session.theme = theme.name
        self.session.save(self._session_path)

    async def on_unmount(self) -> None:
        if self._preview_timer is not None:
            self._preview_timer.stop()
        self.session.folder = str(self.folder)
        self.session.save(self._session_path)
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                logging.exception("could not disconnect")

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield SystemCommand("Go to", "Open a folder by its path", self.action_goto)
        yield SystemCommand("Options", "Colors, size limit, scale, label", self.action_options)
        yield SystemCommand("Store in slots", "Store the marked files, or all files of the folder", self.action_store)
        yield SystemCommand("Store folder and subfolders", "Store all files below this folder", self.action_store_all)
        yield SystemCommand("Clear slots", "Delete everything stored on the display", self.action_clear_slots)
        yield SystemCommand("Brightness", "Set the brightness of the display", self.action_brightness)
        yield SystemCommand("Show the clock", "Switch the display to the clock", self.action_clock)
        yield SystemCommand("Displays", "Search for displays and choose one", self.action_devices)
        yield SystemCommand("Reconnect", "Connect to the display again", self.action_reconnect)
        yield SystemCommand("Mark all", "Mark all files of the folder", self.action_mark_all)
        yield SystemCommand("Unmark all", "Forget the marked files", self.action_unmark_all)

    # messages: shown in the status bar instead of on top of the other panels

    def notify(self, message: str, *, title: str = "", severity="information", timeout: float | None = None,
               markup: bool = True) -> None:
        self.show_message(message, severity, timeout)

    def show_message(self, text: str, severity: str = "information", timeout: float | None = None) -> None:
        self._message_id += 1
        message_id = self._message_id
        self._message_shown_at = time.monotonic()
        try:
            self.query_one("#message", Static).update(Text(text, style=MESSAGE_STYLES.get(severity, "")))
        except NoMatches:
            return
        self.set_timer(timeout or MESSAGE_SECONDS.get(severity, 5), lambda: self._clear_message(message_id))

    def _clear_message(self, message_id: int | None = None) -> None:
        if message_id is not None and message_id != self._message_id:
            return
        try:
            self.query_one("#message", Static).update("")
        except NoMatches:
            pass

    def on_key(self, event: Key) -> None:
        if self._message_id and time.monotonic() - self._message_shown_at >= MESSAGE_MIN_SECONDS:
            self._clear_message()
        self._filter_key(event)

    # the file list

    def reload(self, restore: bool = False) -> None:
        """Fills the list with the folder. The cursor stays on the same name if it can, or goes to the one that was
        selected last time in this folder (restore)."""
        table = self.query_one("#files", DataTable)
        width = table.size.width - table.scrollbar_size_vertical or DEFAULT_TABLE_WIDTH
        name_width = max(width - TABLE_FIXED_WIDTH, NAME_COLUMN_MIN_WIDTH)
        selected = self._selected_key()
        self._loading = True
        table.clear(columns=True)
        table.add_column("", width=1, key="mark")
        table.add_column("Name", width=name_width, key="name")
        table.add_column("Size", width=SIZE_COLUMN_WIDTH, key="size")
        entries = list_folder(self.folder, self.text_filter)
        for entry in entries:
            table.add_row(self._mark(entry.path), fit_name(entry.name, name_width),
                          "" if entry.is_dir else format_size(entry.size), key=str(entry.path))
        names = [str(entry.path) for entry in entries]
        if restore:
            remembered = self.session.selection(self.folder)
            name, index = remembered if remembered else (None, 0)
            row = restore_index([Path(n).name for n in names], name, index)
        else:
            row = names.index(selected) if selected in names else min(table.cursor_row, max(len(names) - 1, 0))
        if names:
            table.move_cursor(row=row)
        self._loading = False
        self.query_one("#left").border_subtitle = self._folder_title(width)
        self._schedule_preview()

    def _folder_title(self, width: int) -> str:
        text = str(self.folder)
        room = max(width - 2, 10)
        return text if len(text) <= room else "…" + text[-(room - 1):]

    def table_resized(self, width: int) -> None:
        # the names are shortened to the width of the list, so the list never scrolls sideways
        if width != self._table_width:
            self._table_width = width
            self.call_after_refresh(self.reload)

    def _mark(self, path: Path) -> str:
        return "✓" if path in self.marked else ""

    def _selected_key(self) -> str | None:
        table = self.query_one("#files", DataTable)
        if table.row_count == 0:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def selected_path(self) -> Path | None:
        key = self._selected_key()
        return None if key is None else Path(key)

    def _entry(self, path: Path) -> Entry | None:
        for entry in list_folder(self.folder, self.text_filter):
            if entry.path == path:
                return entry
        return None

    def action_parent(self) -> None:
        if isinstance(self.focused, Input):
            return
        if self.folder.parent != self.folder:
            self._go_to(self.folder.parent, select=self.folder)

    def action_goto(self) -> None:
        def chosen(path: Path | None) -> None:
            if path is None:
                return
            if path.is_dir():
                self._go_to(path)
            else:
                self._go_to(path.parent, select=path)

        self.push_screen(PathDialog(self.folder), chosen)

    def action_enter(self) -> None:
        path = self.selected_path()
        if path is not None and path.is_dir():
            self._go_to(path)

    def _go_to(self, folder: Path, select: Path | None = None) -> None:
        if select is not None:
            self.session.remember_selection(folder, select.name, 0)
        self.folder = folder
        self.text_filter = ""
        self.query_one("#filter", Input).value = ""
        self.reload(restore=True)

    @on(DataTable.RowSelected)
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        path = Path(event.row_key.value)
        if path.is_dir():
            self._go_to(path)
        elif is_supported(path):
            self.run_device("Showing " + path.name, lambda: self._show(path))

    @on(DataTable.RowHighlighted)
    def _row_highlighted(self) -> None:
        # not the row of the event: the events of a reload arrive when the cursor is already where it belongs
        path = self.selected_path()
        if path is not None and not self._loading and not self.text_filter:
            self.session.remember_selection(self.folder, path.name, self.query_one("#files", DataTable).cursor_row)
        self._schedule_preview()

    # marking

    def action_mark(self) -> None:
        path = self.selected_path()
        if path is None or path.is_dir():
            return
        if path in self.marked:
            self.marked.remove(path)
        else:
            self.marked.append(path)
        table = self.query_one("#files", DataTable)
        table.update_cell(str(path), "mark", self._mark(path))
        if table.cursor_row + 1 < table.row_count:
            table.move_cursor(row=table.cursor_row + 1)
        self._update_info()

    def action_extend(self, delta: int) -> None:
        """Marks the selected file and the one the cursor moves to (Shift+↑/↓)."""
        table = self.query_one("#files", DataTable)
        for _ in range(2):
            path = self.selected_path()
            if path is not None and not path.is_dir() and path not in self.marked:
                self.marked.append(path)
                table.update_cell(str(path), "mark", self._mark(path))
            if _ == 0:
                row = table.cursor_row + delta
                if not 0 <= row < table.row_count:
                    break
                table.move_cursor(row=row)
        self._update_info()

    def action_mark_all(self) -> None:
        for path in files_in(self.folder):
            if path not in self.marked:
                self.marked.append(path)
        self.reload()
        self._update_info()

    def action_unmark_all(self) -> None:
        self.marked.clear()
        self.reload()
        self._update_info()

    # the filter

    def action_filter(self) -> None:
        field = self.query_one("#filter", Input)
        field.add_class("visible")
        field.focus()

    def _filter_key(self, event: Key) -> None:
        field = self.query_one("#filter", Input)
        if not field.has_focus:
            return
        table = self.query_one("#files", DataTable)
        moves = {"up": table.action_cursor_up, "down": table.action_cursor_down,
                 "pageup": table.action_page_up, "pagedown": table.action_page_down}
        if event.key in moves:
            moves[event.key]()
            event.stop()
        elif event.key == "backspace" and not field.value:
            self.action_escape()
            event.stop()

    @on(Input.Changed, "#filter")
    def _filter_changed(self, event: Input.Changed) -> None:
        self.text_filter = event.value
        self.reload()

    @on(Input.Submitted, "#filter")
    def _filter_submitted(self) -> None:
        self.query_one("#files", DataTable).focus()

    def action_escape(self) -> None:
        field = self.query_one("#filter", Input)
        if field.has_class("visible"):
            field.value = ""
            field.remove_class("visible")
            self.query_one("#files", DataTable).focus()
        elif self._busy is not None:
            self._busy.cancel()
        elif self.marked:
            self.action_unmark_all()

    # the preview

    def _schedule_preview(self) -> None:
        if self._preview_timer is not None:
            self._preview_timer.stop()
        self._preview_timer = self.set_timer(PREVIEW_DELAY_SECONDS, self._start_preview)

    def _start_preview(self) -> None:
        try:
            path = self.selected_path()
            widget = self.query_one("#preview", PreviewWidget)
        except NoMatches:  # the timer fired while the app was closing
            return
        self._previewed = path
        self._preview = None
        if path is None:
            widget.show_message("")
            self._update_info()
            return
        if path.is_dir():
            widget.show_message(f"{path.name}/")
            self._update_info()
            return
        widget.show_message("converting…")
        self._update_info()
        options = self.session.options
        self.run_worker(lambda: self._convert(path, options), thread=True, exclusive=True, group="preview")

    def _convert(self, path: Path, options: Options) -> None:
        try:
            preview = convert.convert(path, self.canvas_size, options)
        except Exception as e:
            logging.exception(f"could not convert {path}")
            self.call_from_thread(self._show_preview_error, path, e)
            return
        self.call_from_thread(self._show_preview, path, preview)

    def _show_preview(self, path: Path, preview: Preview) -> None:
        if path != self._previewed:
            return
        self._preview = preview
        try:
            self.query_one("#preview", PreviewWidget).show_frames(preview.frames, preview.durations)
            self._update_info()
        except NoMatches:  # the app closed while the file was converted
            return

    def _show_preview_error(self, path: Path, error: Exception) -> None:
        if path == self._previewed:
            try:
                self.query_one("#preview", PreviewWidget).show_message(f"cannot be shown: {error}")
            except NoMatches:
                return

    @on(PreviewWidget.Fitted)
    def _preview_fitted(self, event: PreviewWidget.Fitted) -> None:
        warning = self.query_one("#preview-warning", Static)
        too_small = event.actual > event.shown > 0
        warning.set_class(too_small, "visible")
        if too_small:
            warning.update(f"⚠ too small: drawn at {event.shown}x{event.shown} of {event.actual}x{event.actual} pixels, "
                           "enlarge the terminal for an exact picture")

    def _update_info(self) -> None:
        path = self._previewed
        lines = []
        if path is not None and not path.is_dir():
            lines.append(path.name)
            if self._preview is not None:
                p = self._preview
                if p.animated:
                    lines.append(f"{len(p.frames)} frames, {p.loop_seconds:.1f} s loop")
                lines.append(f"{p.size_bytes / 1024:.0f} KB to send, about {p.upload_seconds:.0f} s")
        lines.append(f"options: {self.session.options.summary()}")
        if self.marked:
            lines.append(f"{len(self.marked)} marked")
        self.query_one("#info", Static).update("\n".join(lines))

    # the connection and the device

    def _update_status(self) -> None:
        symbols = {"connected": "●", "connecting": "…", "failed": "✗"}
        text = Text(" iDotMatrix ", style="bold")
        text.append(symbols.get(self.connection, "○"), style=STATUS_COLORS.get(self.connection, "grey62"))
        text.append(f" {self.connection}")
        if self.connection == "connected":
            text.append(f" {self.canvas_size}x{self.canvas_size}")
        if self.session.address:
            known = self.session.device(self.session.address)
            name = self._device_names.get(self.session.address) or (known.name if known else "")
            text.append(f"  {name + ' ' if name else ''}{self.session.address}", style="dim")
        elif self.connection != "connecting":
            text.append("  no display chosen, press d", style="dim")
        self.query_one("#status", Static).update(text)

    async def _connect(self) -> None:
        self.connection = "connecting"
        self._update_status()
        try:
            if self.client is not None:
                try:
                    await self.client.disconnect()
                except Exception:
                    logging.exception("could not disconnect")
            self.client = self._client_factory(self.session.address)
            await self._connect_client()
            size = self.client.screen_size
            self.canvas_size = size.value[0] if isinstance(size, ScreenSize) else DEFAULT_CANVAS_SIZE
            self.connection = "connected"
            address = self.session.address
            if address:
                self.session.remember(address, self._device_names.get(address, ""))
                self.session.save(self._session_path)
        except Exception as e:
            logging.exception("could not connect")
            self.connection = "failed"
            self.notify(f"Could not connect: {e}", severity="error", timeout=10)
            if not self.screen_stack[1:]:
                self.action_devices()
        self._update_status()

    async def _connect_client(self) -> None:
        # BlueZ answers InProgress while the search that was running in the device list is still shutting down
        for attempt in range(CONNECT_ATTEMPTS):
            try:
                await self.client.connect()
                return
            except Exception as e:
                if "InProgress" not in str(e) or attempt == CONNECT_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(CONNECT_RETRY_SECONDS)

    def action_devices(self) -> None:
        if self._busy is not None:
            self.notify("Wait for the running upload, or cancel it with Escape", severity="warning")
            return
        if isinstance(self.screen, DevicesScreen):
            return
        connected = self.session.address if self.connection == "connected" else None
        screen = DevicesScreen(self._scanner, self.session.devices, connected=connected, forget=self._forget_device)

        def chosen(address: str | None) -> None:
            self._device_names.update(screen.names)
            if address is None or (address == connected):
                return
            self.session.address = address
            self.action_reconnect()

        self.push_screen(screen, chosen)

    def _forget_device(self, address: str) -> None:
        self.session.forget(address)
        self.session.save(self._session_path)
        self._update_status()

    def action_reconnect(self) -> None:
        self.run_worker(self._connect(), name="connect", exclusive=True, group="connect")

    def run_device(self, label: str, operation: Callable[[], object]) -> None:
        """Runs an operation on the display, one at a time, with the activity bar."""
        if self._busy is not None:
            self.notify("Wait for the running upload, or cancel it with Escape", severity="warning")
            return
        if self.connection != "connected" or self.client is None:
            self.notify("Not connected, press r to try again", severity="warning")
            return
        self._set_activity(label)
        self._busy = self.run_worker(self._run_operation(label, operation), group="device")

    async def _run_operation(self, label: str, operation: Callable[[], object]) -> None:
        try:
            await operation()
        except asyncio.CancelledError:
            self.notify("Cancelled, the display may show an incomplete upload", severity="warning")
            raise
        except Exception as e:
            logging.exception(label)
            self.notify(f"{label} failed: {e}", severity="error", timeout=10)
        finally:
            self._busy = None
            self._set_activity("")

    def _set_activity(self, text: str, done: int | None = None, total: int | None = None) -> None:
        self.query_one("#activity-text", Label).update(text)
        bar = self.query_one("#progress", ProgressBar)
        bar.display = bool(text)
        if done is None or not total:
            bar.update(total=None)
        else:
            bar.update(total=total, progress=done)

    def _upload_progress(self, label: str) -> Callable[[int, int], None]:
        def progress(done: int, total: int) -> None:
            self._set_activity(f"{label}  {done}/{total}", done, total)

        return progress

    def _is_animated(self, path: Path) -> bool:
        return convert.is_animated(path)

    async def _show(self, path: Path) -> None:
        options = self.session.options
        progress = self._upload_progress("Showing " + path.name)
        overlay = options.overlay_for(path)
        if await asyncio.to_thread(self._is_animated, path):
            await self.client.gif.upload_gif_file(
                path, resize_mode=options.resize, colors=options.colors_value, max_size_kb=options.max_size_kb,
                overlay=overlay, progress=progress)
        else:
            await self.client.image.show_image_file(
                path, resize_mode=options.resize, overlay=overlay, progress=progress)
        self.notify(f"Showing {path.name}")

    # the slots

    def action_store(self) -> None:
        files = list(self.marked) or files_in(self.folder)
        self._ask_slots(files)

    def action_store_all(self) -> None:
        self._ask_slots(files_in(self.folder, recursive=True))

    def _ask_slots(self, files: list[Path]) -> None:
        if not files:
            self.notify("No pictures or animations to store", severity="warning")
            return

        def chosen(result: tuple[list[int], int] | None) -> None:
            if result is None:
                return
            slots, display_time = result
            self.session.slots, self.session.display_time = slots, display_time
            self.session.save(self._session_path)
            self.run_device(f"Storing {len(files)} files", lambda: self._store(files, slots, display_time))

        self.push_screen(SlideshowDialog(len(files), self.session.slots, self.session.display_time), chosen)

    async def _store(self, files: list[Path], slots: list[int], display_time: int) -> None:
        options = self.session.options
        label = f"Storing {len(files)} files"

        def progress(number: int, count: int, done: int, total: int) -> None:
            self._set_activity(f"{label}: file {number}/{count}  {done}/{total}", done, total)

        used = await self.client.materials.store(
            [str(file) for file in files], slots=slots, display_time=display_time, resize_mode=options.resize,
            colors=options.colors_value, max_size_kb=options.max_size_kb, overlay=options.overlay_for,
            progress=progress)
        self.notify(f"Stored {len(files)} files in the slots {sorted(used)}, the display cycles through them")

    def action_clear_slots(self) -> None:
        def confirmed(result) -> None:
            if result:
                self.run_device("Clearing the slots", self._clear)

        self.push_screen(ConfirmDialog("Clear slots", "Delete everything that is stored on the display?"), confirmed)

    async def _clear(self) -> None:
        await self.client.materials.clear()
        self.notify("The slots are empty")

    # the rest of the device

    def action_options(self) -> None:
        def chosen(options: Options | None) -> None:
            if options is not None:
                self.session.options = options
                self.session.save(self._session_path)
                self._schedule_preview()

        self.push_screen(OptionsDialog(self.session.options), chosen)

    def action_brightness(self) -> None:
        def chosen(value: int | None) -> None:
            if value is not None:
                self.session.brightness = value
                self.session.save(self._session_path)
                self.run_device("Setting the brightness", lambda: self.client.set_brightness(value))

        self.push_screen(
            NumberDialog("Brightness", "Percent (5 to 100)", self.session.brightness, 5, 100), chosen)

    def action_clock(self) -> None:
        self.run_device("Showing the clock", self._clock)

    async def _clock(self) -> None:
        await self.client.clock.show()
