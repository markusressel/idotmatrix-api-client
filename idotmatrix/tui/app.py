import asyncio
import logging
from collections.abc import Callable, Iterable
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Input, Label, ProgressBar, Static
from textual.worker import Worker

from idotmatrix.client import IDotMatrixClient
from idotmatrix.screensize import ScreenSize
from idotmatrix.tui import convert
from idotmatrix.tui.convert import Preview
from idotmatrix.tui.dialogs import ConfirmDialog, NumberDialog, OptionsDialog, SlideshowDialog
from idotmatrix.tui.files import Entry, files_in, format_size, is_supported, list_folder
from idotmatrix.tui.preview import PreviewWidget
from idotmatrix.tui.settings import Options, Session

logging = logging.getLogger(__name__)

PARENT_KEY = ".."
PREVIEW_DELAY_SECONDS = 0.25
DEFAULT_CANVAS_SIZE = 64


def default_client_factory(address: str | None) -> IDotMatrixClient:
    return IDotMatrixClient(mac_address=address, install_signal_handlers=False)


class IDotMatrixApp(App):
    """Browse a folder, see what a file looks like on the display, and send it."""

    TITLE = "iDotMatrix"
    CSS = """
    #status { height: 1; padding: 0 1; background: $boost; }
    #main { height: 1fr; }
    #left { width: 50%; }
    #right { width: 50%; border-left: solid $primary; }
    #path { height: 1; padding: 0 1; text-style: bold; }
    #filter { display: none; }
    #filter.visible { display: block; }
    #files { height: 1fr; }
    #preview { height: 1fr; min-height: 8; }
    #info { height: auto; max-height: 12; padding: 0 1; border-top: solid $primary; }
    #activity { height: 1; padding: 0 1; }
    #activity Label { width: 1fr; }
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
        Binding("r", "reconnect", "Reconnect"),
        Binding("backspace,left,h", "parent", "Up", show=False),
        Binding("slash", "filter", "Filter"),
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
    ):
        super().__init__()
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

    # layout

    def compose(self) -> ComposeResult:
        yield Static("", id="status")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Static("", id="path")
                yield Input(placeholder="filter", id="filter")
                yield DataTable(id="files", cursor_type="row", zebra_stripes=True)
            with Vertical(id="right"):
                yield PreviewWidget(id="preview")
                yield Static("", id="info")
        with Horizontal(id="activity"):
            yield Label("", id="activity-text")
            yield ProgressBar(id="progress", show_eta=False, total=100)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#files", DataTable)
        table.add_column("", width=1, key="mark")
        table.add_column("Name", key="name")
        table.add_column("Size", key="size")
        self.query_one("#progress", ProgressBar).display = False
        self.reload()
        self._update_status()
        table.focus()
        self.run_worker(self._connect(), name="connect", exclusive=True, group="connect")

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
        yield SystemCommand("Options", "Colors, size limit, scale, label", self.action_options)
        yield SystemCommand("Store in slots", "Store the marked files, or all files of the folder", self.action_store)
        yield SystemCommand("Store folder and subfolders", "Store all files below this folder", self.action_store_all)
        yield SystemCommand("Clear slots", "Delete everything stored on the display", self.action_clear_slots)
        yield SystemCommand("Brightness", "Set the brightness of the display", self.action_brightness)
        yield SystemCommand("Show the clock", "Switch the display to the clock", self.action_clock)
        yield SystemCommand("Reconnect", "Connect to the display again", self.action_reconnect)
        yield SystemCommand("Mark all", "Mark all files of the folder", self.action_mark_all)
        yield SystemCommand("Unmark all", "Forget the marked files", self.action_unmark_all)

    # the file list

    def reload(self) -> None:
        """Fills the list with the folder, and keeps the cursor on the same name if it can."""
        table = self.query_one("#files", DataTable)
        selected = self._selected_key()
        table.clear()
        if self.folder.parent != self.folder:
            table.add_row("", "../", "", key=PARENT_KEY)
        for entry in list_folder(self.folder, self.text_filter):
            table.add_row(self._mark(entry.path), entry.name, "" if entry.is_dir else format_size(entry.size),
                          key=str(entry.path))
        if selected is not None and selected in {key.value for key in table.rows}:
            table.move_cursor(row=table.get_row_index(selected))
        self.query_one("#path", Static).update(str(self.folder))
        self._schedule_preview()

    def _mark(self, path: Path) -> str:
        return "✓" if path in self.marked else ""

    def _selected_key(self) -> str | None:
        table = self.query_one("#files", DataTable)
        if table.row_count == 0:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def selected_path(self) -> Path | None:
        key = self._selected_key()
        return None if key in (None, PARENT_KEY) else Path(key)

    def _entry(self, path: Path) -> Entry | None:
        for entry in list_folder(self.folder, self.text_filter):
            if entry.path == path:
                return entry
        return None

    def action_parent(self) -> None:
        if self.focused is not None and isinstance(self.focused, Input):
            return
        if self.folder.parent != self.folder:
            self._go_to(self.folder.parent, select=self.folder)

    def _go_to(self, folder: Path, select: Path | None = None) -> None:
        self.folder = folder
        self.text_filter = ""
        self.query_one("#filter", Input).value = ""
        self.reload()
        if select is not None:
            table = self.query_one("#files", DataTable)
            if str(select) in {key.value for key in table.rows}:
                table.move_cursor(row=table.get_row_index(str(select)))

    @on(DataTable.RowSelected)
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if key == PARENT_KEY:
            self.action_parent()
            return
        path = Path(key)
        if path.is_dir():
            self._go_to(path)
        elif is_supported(path):
            self.run_device("Showing " + path.name, lambda: self._show(path))

    @on(DataTable.RowHighlighted)
    def _row_highlighted(self) -> None:
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
        self.query_one("#preview", PreviewWidget).show_frames(preview.frames, preview.durations)
        self._update_info()

    def _show_preview_error(self, path: Path, error: Exception) -> None:
        if path == self._previewed:
            self.query_one("#preview", PreviewWidget).show_message(f"cannot be shown: {error}")

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
        text.append(f"{symbols.get(self.connection, '○')} {self.connection}")
        if self.connection == "connected":
            text.append(f" {self.canvas_size}x{self.canvas_size}")
        if self.session.address:
            text.append(f"  {self.session.address}", style="dim")
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
            await self.client.connect()
            size = self.client.screen_size
            self.canvas_size = size.value[0] if isinstance(size, ScreenSize) else DEFAULT_CANVAS_SIZE
            self.connection = "connected"
        except Exception as e:
            logging.exception("could not connect")
            self.connection = "failed"
            self.notify(f"Could not connect: {e}", severity="error", timeout=10)
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
