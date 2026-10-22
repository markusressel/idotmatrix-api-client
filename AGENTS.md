# AGENTS.md

Async Python library for controlling iDotMatrix BLE pixel displays (16x16, 32x32, 64x64). Fork of
`derkalle4/python3-idotmatrix-library`, reverse engineered from the iDotMatrix Android app (`BleProtocolN.java`).
Not API-compatible with the original.

## Setup

- Python `>=3.12,<3.15`, packaging via Poetry (`poetry-core`).
- Install: `poetry install --with test` (venv at `.venv`).
- Runtime deps: `bleak` (BLE), `pillow`, `watchdog`, `cryptography`.

## Commands

```sh
just test                 # all tests (runs from tests/, like CI); extra args go to pytest
just test clock_module_test.py::TestClockModule::test_show
just coverage             # line coverage with missing lines
just lint                 # same flake8 checks as CI
just build                # poetry build
```

`make <target>` proxies to `just <target>`. Without `just`/`uv`, use `poetry install --with test` and `cd tests && pytest`.

CI (`.github/workflows/pythonpackage.yml`) runs on Python 3.12 and 3.13. Keep code compatible with both.

## Layout

```
idotmatrix/
  client.py              IDotMatrixClient: public entry point, exposes one property per module
  connection_manager.py  BLE connection, send_bytes, auto-reconnect, listeners
  screensize.py          ScreenSize enum
  const.py               BLE UUIDs and constants
  digital_picture_frame.py
  modules/               one class per device feature (clock, text, gif, image, ...)
    __init__.py          IDotMatrixModule base class (_send_bytes, _connect)
  util/                  color_utils, image_utils, file_watch
tests/                   *_module_test.py, one per module; shared TestBase in tests/__init__.py
example*.py              runnable usage examples (need a real device)
```

## Conventions

- Everything that talks to the device is `async`. Never block the event loop; use `asyncio.sleep`.
- Each feature module subclasses `IDotMatrixModule`, takes a `ConnectionManager`, and sends via
  `self._send_bytes(data=..., response=...)`. Do not call `bleak` directly from modules.
- Commands are raw byte payloads (`bytearray([len, 0, cmd, ...])`). Document the source in the docstring
  (`Based on the BleProtocolN.java file ...`). Public methods do not return raw bytes (dropped by design).
- New module checklist: add `idotmatrix/modules/<name>.py`, register a property on `IDotMatrixClient`
  in `client.py`, add `tests/<name>_module_test.py`.
- Validate args and raise `ValueError` with a clear message (see `ClockModule.show`). Accept enums or ints,
  and colors via `color_utils.parse_color_rgb`.
- Module-level `logging = logging.getLogger(__name__)` pattern is used on module classes; match it.
- Docstrings: Google style (`Args:`), as in existing modules.
- 4-space indent, max line length 127 (flake8 config in CI).

## Testing

- Test classes extend `tests.TestBase`; `asyncio_mode = auto`, so write plain `async def test_*`.
- Mock the transport: `connection_manager = AsyncMock()`, then assert
  `connection_manager.send_bytes.assert_awaited_once_with(data=bytearray(b'...'), response=False)`.
- Assert exact byte payloads. A changed byte means a changed wire protocol; do not "fix" expected bytes
  without confirming against the protocol source or a real device.
- Use GIVEN / WHEN / THEN comments, as existing tests do.
- Tests must not need hardware or Bluetooth.

## Boundaries

- Ask before changing existing payload bytes, BLE UUIDs, or public method signatures: users depend on them.
- Do not add dependencies without need; update `pyproject.toml` and `poetry.lock` together (`poetry lock`).
- Do not commit `.venv/` or `.idea/`.
- `idotmatrix/fonts/` and `images/` are bundled assets; keep license files with them.
- Examples (`example*.py`) hit real hardware. Do not run them in automated checks.
