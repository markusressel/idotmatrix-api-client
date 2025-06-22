from collections.abc import Callable
from pathlib import Path
from typing import Dict

from watchdog.events import FileSystemEventHandler, EVENT_TYPE_MODIFIED, EVENT_TYPE_MOVED, EVENT_TYPE_CREATED, \
    EVENT_TYPE_DELETED, FileSystemEvent


class EventHandler(FileSystemEventHandler):

    def __init__(
        self,
        on_created: Callable[[Path], None] = None,
        on_modified: Callable[[Path], None] = None,
        on_moved: Callable[[Path, Path], None] = None,
        on_deleted: Callable[[Path], None] = None,
    ):
        super().__init__()
        self.on_created_callback = on_created if on_created else lambda _: None
        self.on_modified_callback = on_modified if on_modified else lambda _: None
        self.on_moved_callback = on_moved if on_moved else lambda _, __: None
        self.on_deleted_callback = on_deleted if on_deleted else lambda _: None

    def on_any_event(self, event: FileSystemEvent):
        # TODO: Implement filtering logic if needed
        # if not self._event_matches_filter(event):
        #    return

        _actions: Dict[str, Callable[FileSystemEvent]] = {
            EVENT_TYPE_CREATED: self.created,
            EVENT_TYPE_MODIFIED: self.modified,
            EVENT_TYPE_MOVED: self.moved,
            EVENT_TYPE_DELETED: self.deleted,
        }
        _actions[event.event_type](event)

    def created(self, event):
        self.on_created_callback(Path(event.src_path))

    def modified(self, event):
        self.on_modified_callback(Path(event.src_path))

    def moved(self, event):
        self.on_moved_callback(Path(event.src_path), Path(event.dest_path))

    def deleted(self, event):
        self.on_deleted_callback(Path(event.src_path))
