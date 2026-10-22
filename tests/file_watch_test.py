import re
from pathlib import Path
from unittest.mock import MagicMock

from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent, FileMovedEvent, DirCreatedEvent

from tests import TestBase


class TestImageFileEventHandler(TestBase):

    def _handler(self, **callbacks):
        # importing here so a broken import shows up as a test failure, not a collection error
        from idotmatrix.util.file_watch import ImageFileEventHandler
        pattern = re.compile(r".*\.(png|gif)$")
        return ImageFileEventHandler(file_filter=pattern, **callbacks)

    def test_module_is_importable(self):
        import idotmatrix.util.file_watch  # noqa: F401

    def test_created_event_calls_callback(self):
        on_created = MagicMock()
        self._handler(on_created=on_created).on_any_event(FileCreatedEvent("/x/a.png"))
        on_created.assert_called_once_with(Path("/x/a.png"))

    def test_modified_event_calls_callback(self):
        on_modified = MagicMock()
        self._handler(on_modified=on_modified).on_any_event(FileModifiedEvent("/x/a.png"))
        on_modified.assert_called_once_with(Path("/x/a.png"))

    def test_deleted_event_calls_callback(self):
        on_deleted = MagicMock()
        self._handler(on_deleted=on_deleted).on_any_event(FileDeletedEvent("/x/a.png"))
        on_deleted.assert_called_once_with(Path("/x/a.png"))

    def test_moved_event_calls_callback(self):
        on_moved = MagicMock()
        self._handler(on_moved=on_moved).on_any_event(FileMovedEvent("/x/a.png", "/x/b.png"))
        on_moved.assert_called_once_with(Path("/x/a.png"), Path("/x/b.png"))

    def test_non_matching_file_is_ignored(self):
        on_created = MagicMock()
        self._handler(on_created=on_created).on_any_event(FileCreatedEvent("/x/a.txt"))
        on_created.assert_not_called()

    def test_directories_are_ignored(self):
        on_created = MagicMock()
        self._handler(on_created=on_created).on_any_event(DirCreatedEvent("/x/dir.png"))
        on_created.assert_not_called()

    def test_missing_callbacks_are_noops(self):
        self._handler().on_any_event(FileCreatedEvent("/x/a.png"))
