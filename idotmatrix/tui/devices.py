import asyncio
import logging
import re
import time
from collections.abc import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Label

from idotmatrix.tui.scanner import DeviceScanner, Found
from idotmatrix.tui.settings import KnownDevice

logging = logging.getLogger(__name__)

SCAN_SECONDS = 4.0
RESCAN_PAUSE_SECONDS = 0.5
# a display that did not advertise in the last scans is shown as offline
ONLINE_FOR_SECONDS = 12.0
ADDRESS_PATTERN = re.compile(r"^\S{6,}$")


def format_ago(then: float | None, now: float) -> str:
    if then is None:
        return "never"
    seconds = max(0, int(now - then))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


class DevicesScreen(ModalScreen[str | None]):
    """
    Searches for displays while it is open, and lists them together with the ones connected to before, with their
    state: connected, online (advertising, with the signal strength) or offline. Enter connects, it returns the address.
    """

    BINDINGS = [
        Binding("enter", "connect", "Connect"),
        Binding("r", "rescan", "Search again"),
        Binding("a", "add", "Add address"),
        Binding("f", "forget", "Forget"),
        Binding("escape", "close", "Close"),
    ]

    DEFAULT_CSS = """
    DevicesScreen { align: center middle; }
    DevicesScreen > Vertical {
        width: 90; max-width: 95%; height: 22; max-height: 90%;
        border: round $primary; border-title-color: $primary; border-title-style: bold;
        background: $surface; padding: 0 1;
    }
    DevicesScreen DataTable { height: 1fr; background: $surface; }
    DevicesScreen #scan-state { height: 1; color: $text-muted; }
    DevicesScreen #address { display: none; margin-bottom: 1; }
    DevicesScreen #address.visible { display: block; }
    DevicesScreen Footer { background: $surface; }
    """

    def __init__(
        self,
        scanner: DeviceScanner,
        known: list[KnownDevice],
        connected: str | None = None,
        forget: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        super().__init__()
        self._scanner = scanner
        self._known = {device.address: device for device in known}
        self._connected = connected
        self._forget = forget
        self._clock = clock
        self._seen: dict[str, tuple[Found, float]] = {}
        self._scanning = False
        self.scan_count = 0  # finished searches
        self._scan_error: str | None = None
        self.names: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = "Displays"
            box.border_subtitle = "Enter connects"
            yield Label("", id="scan-state")
            yield Input(placeholder="Bluetooth address, then Enter", id="address")
            yield DataTable(id="devices", cursor_type="row", zebra_stripes=True)
            yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#devices", DataTable)
        table.add_column("State", key="state")
        table.add_column("Name", key="name")
        table.add_column("Address", key="address")
        table.add_column("Last connected", key="last")
        table.focus()
        self.refresh_rows()
        self.run_worker(self._scan_loop(), name="scan", exclusive=True, group="scan")

    def on_unmount(self) -> None:
        self.workers.cancel_group(self, "scan")

    # scanning

    async def _scan_loop(self) -> None:
        while True:
            await self.scan_once()
            await asyncio.sleep(RESCAN_PAUSE_SECONDS)

    async def scan_once(self) -> None:
        self._scanning = True
        try:
            self._update_state()
        except NoMatches:
            return
        try:
            found = await self._scanner.scan(SCAN_SECONDS)
            self._scan_error = None
            now = self._clock()
            for item in found:
                self._seen[item.address] = (item, now)
                if item.name:
                    self.names[item.address] = item.name
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.exception("scan failed")
            self._scan_error = str(e) or type(e).__name__
        finally:
            self._scanning = False
            self.scan_count += 1
        try:
            self.refresh_rows()
            self._update_state()
        except NoMatches:  # the screen was closed while the search ran
            return

    def _update_state(self) -> None:
        if self._scan_error:
            text = Text(f"Search failed: {self._scan_error}", style="red")
        elif self._scanning:
            text = Text("Searching…")
        else:
            text = Text("Searched. Displays that are connected to another device (the app) do not show up.")
        self.query_one("#scan-state", Label).update(text)

    def action_rescan(self) -> None:
        self.run_worker(self._scan_loop(), name="scan", exclusive=True, group="scan")

    # the list

    def state_of(self, address: str, now: float) -> tuple[str, int]:
        """The state shown for a device, and the order: connected, online (strongest first), offline."""
        if address == self._connected:
            return "● connected", 0
        seen = self._seen.get(address)
        if seen is not None and now - seen[1] <= ONLINE_FOR_SECONDS:
            rssi = seen[0].rssi
            return ("● online" + (f" {rssi} dBm" if rssi is not None else "")), 1
        return "○ offline", 2

    def rows(self) -> list[tuple[str, str, str, str, str]]:
        """(address, state, name, address, last connected) of every device, in order."""
        now = self._clock()
        addresses = list(dict.fromkeys([*self._known, *self._seen, *([self._connected] if self._connected else [])]))
        rows = []
        for address in addresses:
            known = self._known.get(address)
            seen = self._seen.get(address)
            state, order = self.state_of(address, now)
            name = (seen[0].name if seen else "") or (known.name if known else "") or "iDotMatrix"
            last = format_ago(known.last_connected, now) if known else "new"
            rssi = seen[0].rssi if seen and seen[0].rssi is not None else -999
            rows.append((order, -rssi, address, state, name, last))
        rows.sort()
        return [(address, state, name, address, last) for _, _, address, state, name, last in rows]

    def refresh_rows(self) -> None:
        table = self.query_one("#devices", DataTable)
        selected = self._selected()
        table.clear()
        for address, state, name, shown, last in self.rows():
            style = "green" if state.startswith("● ") else "dim"
            table.add_row(Text(state, style=style), name, shown, last, key=address)
        if selected is not None and selected in {key.value for key in table.rows}:
            table.move_cursor(row=table.get_row_index(selected))
        if table.row_count == 0:
            self.query_one("#scan-state", Label).update("No display found yet. Press a to enter an address.")

    def _selected(self) -> str | None:
        table = self.query_one("#devices", DataTable)
        if table.row_count == 0:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    # actions

    def action_connect(self) -> None:
        if self.query_one("#address", Input).has_focus:
            return
        address = self._selected()
        if address is not None:
            self.dismiss(address)

    def on_data_table_row_selected(self) -> None:
        self.action_connect()

    def action_forget(self) -> None:
        address = self._selected()
        if address is None or self._forget is None:
            return
        self._forget(address)
        self._known.pop(address, None)
        self._seen.pop(address, None)
        self.refresh_rows()

    def action_add(self) -> None:
        field = self.query_one("#address", Input)
        field.add_class("visible")
        field.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        address = event.value.strip()
        if not ADDRESS_PATTERN.match(address):
            self.query_one("#scan-state", Label).update(Text("That is not an address", style="red"))
            return
        self.dismiss(address)

    def action_close(self) -> None:
        field = self.query_one("#address", Input)
        if field.has_class("visible"):
            field.remove_class("visible")
            field.value = ""
            self.query_one("#devices", DataTable).focus()
        else:
            self.dismiss(None)
