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

CI (`.github/workflows/pythonpackage.yml`) runs on Python 3.12, 3.13 and 3.14. Keep code compatible with all of them.

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
  util/                  color_utils, image_utils, file_watch, upload_ack, device_material
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

## Device protocol notes (from the decompiled official app and tests on a 64x64)

- Image and GIF uploads send 4096 byte chunks, each with a header. The device acknowledges every chunk with a
  notification on `fa03` (`05 00 <type> 00 <status>`, see `util/upload_ack.py`). The next chunk must not be sent before
  that (`send_packets(wait_for_ack=True)`), or the device drops data and rejects uploads (status `00`).
- The device skips an upload of data it already has (answers `finished` right away).
- Upload types: GIF = 1, static image = 2, DIY image = 0. The last header byte is an index: 0 to 11 are slots the
  device keeps, 13 shows the item right away (what the app uses for photos and GIFs), 12 is used for text.
- The official app shows photos with a static image upload (`ImageModule.show_image_file`). The DIY mode is for drawing,
  switching between it and GIFs needs `DisableDIY`, a black screen and `reset()`, and was unreliable (rejected uploads,
  rainbow flash, one device reset). Do not reintroduce mode switching.
- All frames of a GIF need color tables of the same size. PIL trims them to the used colors, so they are padded to 256
  entries (`image_utils.pad_palette`), otherwise the device garbles or drops frames.
- Not verified on a device: `GifModule.clear_storage` (the app's "delete all materials" command).

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
