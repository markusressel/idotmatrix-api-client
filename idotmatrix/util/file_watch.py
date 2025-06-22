from collections.abc import Callable
from pathlib import Path
from typing import Dict

from dulwich.ignore import Pattern
from watchdog.events import FileSystemEventHandler, EVENT_TYPE_MODIFIED, EVENT_TYPE_MOVED, EVENT_TYPE_CREATED, \
    EVENT_TYPE_DELETED, FileSystemEvent


class ImageFileEventHandler(FileSystemEventHandler):

    def __init__(
        self,
        file_filter: Pattern,
        on_created: Callable[[Path], None] = None,
        on_modified: Callable[[Path], None] = None,
        on_moved: Callable[[Path, Path], None] = None,
        on_deleted: Callable[[Path], None] = None,
    ):
        super().__init__()
        self._file_filter = file_filter
        self._on_created_callback = on_created if on_created else lambda _: None
        self._on_modified_callback = on_modified if on_modified else lambda _: None
        self._on_moved_callback = on_moved if on_moved else lambda _, __: None
        self._on_deleted_callback = on_deleted if on_deleted else lambda _: None

    def on_any_event(self, event: FileSystemEvent):
        # TODO: Implement filtering logic if needed
        if not self._event_matches_filter(event):
            return

        _actions: Dict[str, Callable[[FileSystemEvent], None]] = {
            EVENT_TYPE_CREATED: self.created,
            EVENT_TYPE_MODIFIED: self.modified,
            EVENT_TYPE_MOVED: self.moved,
            EVENT_TYPE_DELETED: self.deleted,
        }
        _actions.get(event.event_type, lambda x: None)(event)

    def created(self, event: FileSystemEvent):
        self._on_created_callback(Path(event.src_path))

    def modified(self, event: FileSystemEvent):
        self._on_modified_callback(Path(event.src_path))

    def moved(self, event: FileSystemEvent):
        self._on_moved_callback(Path(event.src_path), Path(event.dest_path))

    def deleted(self, event: FileSystemEvent):
        self._on_deleted_callback(Path(event.src_path))

    def _event_matches_filter(self, event: FileSystemEvent) -> bool:
        if event.is_directory:
            return False
        return self._file_filter.match(event.dest_path)
