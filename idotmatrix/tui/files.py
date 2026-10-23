import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif"}


@dataclass(frozen=True)
class Entry:
    path: Path
    is_dir: bool
    size: int

    @property
    def name(self) -> str:
        return self.path.name + ("/" if self.is_dir else "")


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def natural_key(name: str) -> list:
    """Sorts `a2` before `a10`."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def list_folder(folder: Path, text_filter: str = "", show_hidden: bool = False) -> list[Entry]:
    """The folders and the pictures and animations in a folder, folders first, in natural order."""
    entries = []
    needle = text_filter.lower()
    try:
        children = list(folder.iterdir())
    except OSError:
        return []
    for child in children:
        if child.name.startswith(".") and not show_hidden:
            continue
        try:
            is_dir = child.is_dir()
            if not is_dir and not (child.is_file() and is_supported(child)):
                continue
            size = 0 if is_dir else child.stat().st_size
        except OSError:
            continue
        if needle and needle not in child.name.lower():
            continue
        entries.append(Entry(child, is_dir, size))
    entries.sort(key=lambda entry: (not entry.is_dir, natural_key(entry.path.name)))
    return entries


def files_in(folder: Path, recursive: bool = False) -> list[Path]:
    """The pictures and animations of a folder (and below it) in natural order."""
    found = []
    for entry in list_folder(folder):
        if entry.is_dir:
            if recursive:
                found.extend(files_in(entry.path, recursive=True))
        else:
            found.append(entry.path)
    return found


def format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
