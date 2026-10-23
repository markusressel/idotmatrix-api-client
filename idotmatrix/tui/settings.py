import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from idotmatrix.util.device_material import SLOTS
from idotmatrix.util.image_utils import ResizeMode
from idotmatrix.util.overlay import POSITIONS, TextOverlay

logging = logging.getLogger(__name__)

COLOR_CHOICES = ("auto", "256", "128", "64", "32", "16")
RESIZE_CHOICES = ("fit", "fill", "stretch", "crop")
LABEL_CHOICES = ("none", "name", "text")
DEFAULT_SLIDESHOW_TIME_SECONDS = 10
DEFAULT_THEME = "nord"


@dataclass
class Options:
    """How files are converted for the display."""
    colors: str = "auto"
    max_size_kb: int | None = None
    resize_mode: str = "fill"
    label: str = "none"
    label_text: str = ""
    label_position: str = "bottom-left"

    def __post_init__(self):
        # a session file may come from another version or be edited by hand
        if self.colors not in COLOR_CHOICES:
            self.colors = "auto"
        if self.resize_mode not in RESIZE_CHOICES:
            self.resize_mode = "fill"
        if self.label not in LABEL_CHOICES:
            self.label = "none"
        if self.label_position not in POSITIONS:
            self.label_position = "bottom-left"
        if not isinstance(self.max_size_kb, int) or isinstance(self.max_size_kb, bool) or self.max_size_kb < 1:
            self.max_size_kb = None

    @property
    def colors_value(self) -> int | str:
        return self.colors if self.colors == "auto" else int(self.colors)

    @property
    def resize(self) -> ResizeMode:
        return ResizeMode[self.resize_mode.upper()]

    def overlay_for(self, path: str | Path) -> TextOverlay | None:
        """The label of a file, or None."""
        if self.label == "name":
            return TextOverlay(Path(path).stem, position=self.label_position)
        if self.label == "text" and self.label_text:
            return TextOverlay(self.label_text, position=self.label_position)
        return None

    def summary(self) -> str:
        parts = [f"colors {self.colors}", f"{self.resize_mode}"]
        if self.max_size_kb:
            parts.append(f"max {self.max_size_kb} KB")
        if self.label != "none":
            parts.append("label: " + ("file name" if self.label == "name" else repr(self.label_text)))
        return ", ".join(parts)


@dataclass
class KnownDevice:
    """A display that was connected to before."""
    address: str
    name: str = ""
    last_connected: float | None = None  # seconds since the epoch

    @property
    def title(self) -> str:
        return self.name or "iDotMatrix"


@dataclass
class Session:
    """What is remembered between runs."""
    folder: str = ""
    address: str | None = None
    options: Options = field(default_factory=Options)
    slots: list[int] = field(default_factory=lambda: list(SLOTS))
    display_time: int = DEFAULT_SLIDESHOW_TIME_SECONDS
    brightness: int = 100
    devices: list[KnownDevice] = field(default_factory=list)
    theme: str = DEFAULT_THEME

    def remember(self, address: str, name: str = "", now: float | None = None) -> None:
        """Adds a device that was connected, or updates it, and makes it the one to connect to next time."""
        known = self.device(address)
        if known is None:
            known = KnownDevice(address)
            self.devices.append(known)
        known.name = name or known.name
        known.last_connected = time.time() if now is None else now
        self.address = address

    def forget(self, address: str) -> None:
        self.devices = [device for device in self.devices if device.address != address]
        if self.address == address:
            self.address = None

    def device(self, address: str | None) -> KnownDevice | None:
        return next((device for device in self.devices if device.address == address), None)

    @staticmethod
    def default_path() -> Path:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        return base / "idotmatrix-tui" / "session.json"

    @classmethod
    def load(cls, path: Path | None = None) -> "Session":
        path = path or cls.default_path()
        try:
            raw = json.loads(path.read_text())
            options = raw.get("options") or {}
            known = {name for name in Options.__dataclass_fields__}
            slots = [slot for slot in raw.get("slots", []) if isinstance(slot, int) and slot in SLOTS]
            return cls(
                folder=str(raw.get("folder") or ""),
                address=raw.get("address") or None,
                options=Options(**{key: value for key, value in options.items() if key in known}),
                slots=sorted(set(slots)) or list(SLOTS),
                display_time=_int_in(raw.get("display_time"), 1, 65535, DEFAULT_SLIDESHOW_TIME_SECONDS),
                brightness=_int_in(raw.get("brightness"), 5, 100, 100),
                devices=_devices(raw.get("devices")),
                theme=raw["theme"] if isinstance(raw.get("theme"), str) and raw["theme"] else DEFAULT_THEME,
            )
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError, TypeError, AttributeError) as e:
            logging.warning(f"ignoring the session file {path}: {e}")
            return cls()

    def save(self, path: Path | None = None) -> None:
        path = path or self.default_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(asdict(self), indent=2))
        except OSError as e:
            logging.warning(f"could not save the session to {path}: {e}")


def _devices(raw) -> list[KnownDevice]:
    devices = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("address"), str) and item["address"]:
            last = item.get("last_connected")
            devices.append(KnownDevice(
                address=item["address"],
                name=item["name"] if isinstance(item.get("name"), str) else "",
                last_connected=float(last) if isinstance(last, (int, float)) and not isinstance(last, bool) else None,
            ))
    return devices


def _int_in(value, low: int, high: int, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
        return value
    return default
