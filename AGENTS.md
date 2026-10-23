# AGENTS.md

Async Python library for controlling iDotMatrix BLE pixel displays (16x16, 32x32, 64x64). Fork of
`derkalle4/python3-idotmatrix-library`, reverse engineered from the iDotMatrix Android app (`BleProtocolN.java`).
Not API-compatible with the original.

The Home Assistant integration built on this library lives in its own repository,
[ha-idotmatrix](https://github.com/markusressel/ha-idotmatrix). It depends on the public API of this library
(`IDotMatrixClient`, `BleakTransport`, `transport_factory`, `set_ble_device`, `install_signal_handlers`), so check that
it keeps working when you change those, and keep the library free of anything that blocks the event loop.

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
  connection_manager.py  connection logic: send_bytes, acks, heartbeat, auto-reconnect, listeners
  protocol.py            Command table (opcode + subcommand) and build_command, which computes the length bytes
  transport.py           Transport protocol (write, notify, MTU) and BleakTransport, which wraps the bleak client
  screensize.py          ScreenSize enum
  const.py               BLE UUIDs and constants
  apps/                  things built on top of the client (digital_picture_frame.py: slideshow of a folder)
  modules/               one class per device feature (clock, text, gif, image, ...)
    __init__.py          IDotMatrixModule base class (_send_bytes, _connect)
  util/                  color_utils, image_utils, file_watch, upload_ack, device_material
tests/                   *_module_test.py, one per module; shared TestBase in tests/__init__.py
example*.py              runnable usage examples (need a real device)
```

## Conventions

- Everything that talks to the device is `async`. Never block the event loop; use `asyncio.sleep`.
- Each feature module subclasses `IDotMatrixModule`, takes a `ConnectionManager`, and sends via
  `self._send_bytes(data=..., response=...)`. Do not call `bleak` directly from modules; the connection manager talks to a `Transport`.
- Commands are built with `protocol.build_command(protocol.SOME_COMMAND, *payload)`, which writes the length bytes. New
  commands get an entry in `protocol.py` (opcode and subcommand), upload headers are still assembled by hand. Document the source in the docstring
  (`Based on the BleProtocolN.java file ...`). Public methods do not return raw bytes (dropped by design).
- New module checklist: add `idotmatrix/modules/<name>.py`, register a property on `IDotMatrixClient`
  in `client.py`, add `tests/<name>_module_test.py`.
- Validate args and raise `ValueError` with a clear message (see `ClockModule.show`). Accept enums or ints,
  and colors via `color_utils.parse_color_rgb`.
- Module-level `logging = logging.getLogger(__name__)` pattern is used on module classes; match it.
- Docstrings: Google style (`Args:`), as in existing modules.
- 4-space indent, max line length 127 (flake8 config in CI).

## Device protocol notes

What we know about the devices is collected in [`docs/DEVICE-PROTOCOL.md`](docs/DEVICE-PROTOCOL.md). Read it before
changing anything that talks to the device. **Keep it up to date**: whenever you learn something about how the devices
behave (from the decompiled app, a device test or a third party), add it there, mark how sure it is (verified / app /
claim / guess), and correct entries that turn out to be wrong. Do this in the same change as the code, and put
anything unverified into `TODO.md` as well.

The most important rules:

- Image and GIF uploads must wait for the acknowledgement of each chunk (`send_packets(wait_for_ack=True)`).
- Show photos with `ImageModule.show_image_file`. Do not reintroduce DIY mode switching in slideshows.
- All frames of a GIF need color tables of the same size (`image_utils.pad_palette`).

## Testing

- Test classes extend `tests.TestBase`; `asyncio_mode = auto`, so write plain `async def test_*`.
- Mock the transport: `connection_manager = AsyncMock()`, then assert
  `connection_manager.send_bytes.assert_awaited_once_with(data=bytearray(b'...'), response=False)`.
- Assert exact byte payloads. A changed byte means a changed wire protocol; do not "fix" expected bytes
  without confirming against the protocol source or a real device.
- Use GIVEN / WHEN / THEN comments, as existing tests do.
- Tests must not need hardware or Bluetooth. To test the connection logic, use `tests.fake_device.FakeDeviceTestBase`
  (a `ConnectionManager` on a `tests.fake_transport.FakeTransport`) instead of patching `bleak`.

## Boundaries

- Ask before changing existing payload bytes, BLE UUIDs, or public method signatures: users depend on them.
- Do not add dependencies without need; update `pyproject.toml` and `poetry.lock` together (`poetry lock`).
- Do not commit `.venv/` or `.idea/`.
- `idotmatrix/fonts/` and `images/` are bundled assets; keep license files with them.
- Examples (`example*.py`) hit real hardware. Do not run them in automated checks.
