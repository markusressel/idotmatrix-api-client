# TODO

Baseline was 25 tests, 44% line coverage. Order: tests first (bug tests written red), then fixes (tests go green).

## 0. Upstream

- [x] Merged PR #12 (BLE MTU fragmentation, fixes #11) and PR #10 (compact fonts) upstream; this branch is rebased on top of them

## 1. Test coverage

- [x] Justfile + Makefile proxy (`just test`, `just coverage`, `just lint`)
- [x] `util/color_utils.py`: ints, hex, `0x`, named, tuples, list, invalid inputs
- [x] `util/image_utils.py`: `palettize`, `resize_image` FIT / FILL / STRETCH
- [x] `connection_manager.py`: connect, disconnect, send_bytes chunking, send_packets, listeners, auto-reconnect
- [x] `client.py`: module properties, connect / disconnect, delegating methods
- [x] `modules/common.py`: all commands
- [x] `modules/system.py`
- [x] `modules/music_sync.py`
- [x] validation (`ValueError`) branches: clock, eco, countdown, fullscreen_color, effect, chronograph, graffiti, text, image, gif
- [x] `util/file_watch.py`
- [x] `digital_picture_frame.py` (smoke tests; found and fixed the folder watching bugs)
- [x] CI: `pytest-cov`, coverage in the job summary, Python 3.14 in the matrix

## 2. Bugs (each has a red test first)

- [x] `connect()` without address deadlocks on `connection_manager_lock`
- [x] `util/file_watch.py`: missing `dulwich` dependency, wrong `Pattern` type, filter uses `dest_path`
- [x] (fixed by PR #10) `ConnectionManager()` raises outside a running event loop; signal handler overrides user's SIGINT, breaks on Windows
- [x] `parse_color_rgb`: `#fff` / `0xfff` shorthand and length check, reject `bool`, bare `except`, rounding of named colours
- [x] `or` used instead of `|` in type hints (`clock.py`, `gif.py`)
- [x] `idotmatrix/__init__.py` does not export `IDotMatrixClient` / `ScreenSize` (README example fails)
- [x] `connect()` notifies listeners when already connected
- [x] `send_bytes` chunk log off by one; `discover_devices` uses root logger

## 3. Cleanup

- [x] Module-level lock -> per-instance lock
- [x] Drop `asyncio` dep (the PyPI package is a Python 3.3 backport that can shadow the stdlib module)
- [x] Drop `matplotlib` (named colours via `PIL.ImageColor`)
- [x] Remove commented-out block in `send_packets`
- [x] Remove duplicate address assignment in `IDotMatrixClient.__init__`
- [x] Stop touching `client._backend.address`
- [x] Reconnect loop backoff
- [x] Cache module instances in `IDotMatrixClient`

## 4. Larger ideas (not started)

- [x] `Transport` protocol + fake device for tests (`idotmatrix/transport.py`, `tests/fake_transport.py`)
- [x] Home Assistant support, first step: `BleakTransport` / `ConnectionManager.set_device` / `IDotMatrixClient(ble_device=...)` take a `BLEDevice`, `transport_factory` allows a custom `Transport`. Not tried inside Home Assistant yet: check the address-less discovery and our auto-reconnect and heartbeat against HA's own reconnect handling (a real integration probably wants to turn them off), and whether it needs `bleak-retry-connector`
- [x] Opcode table / protocol layer (`idotmatrix/protocol.py`: `Command`, `build_command`, used by the modules, the ack table and the heartbeat). Not covered: the text and upload headers, which are assembled by hand
- [x] Moved `digital_picture_frame.py` to `idotmatrix/apps/` (import path changed to `idotmatrix.apps.digital_picture_frame`, no re-export of the old one)
- [x] GIF upload reliability: ack flow control and uniform color table sizes (see commits)

## 5. Verify on a device (README roadmap items without confirmation)

- [x] MusicSync with the device microphone works (`set_mic_type`, fixed). Not done: streaming sound from the computer to the device (`06 00 00 02 <level> 01` for the image scenes, 28 frequency levels for the bar scenes, see docs/DEVICE-PROTOCOL.md), and finding out how many scenes exist
- [ ] Bluetooth password protection: `CommonModule.set_password` exists, but nobody confirmed the whole flow (setting a password, then connecting and authenticating against a protected device)
- [ ] Alarm & Buzzer (see issue #18): no module yet
- [ ] Cloud-API to download / upload images: not started
- [ ] Cloud-firmware update: unknown whether possible
- [ ] Understand the other notifications of the device (only the upload acknowledgements on `fa03` are known, see `util/upload_ack.py`)
- [ ] `GifModule.clear_storage` (the app's "delete all materials" command) has not been tried on a device
- [ ] Uploads on 16x16 and 32x32 devices (tests only use mocks for those sizes)

## 6. Ideas to try on a device

- [x] PNG payload: works on a 64x64 (static and DIY), saves 0.2-0.4 s per upload, opt-in via `show_image_file(png=True)`. Still to check: 16x16 and 32x32 devices, whether it is worth making it the default
- [x] Acknowledgements of normal commands: `send_bytes` waits for them by default for the commands in `util/command_ack.py`
- [x] Heartbeat that detects a silently dead link (`set_heartbeat`, enabled by `DigitalPictureFrame`). Its own dead-link detection is only tested with mocks, BlueZ noticed the power loss first; try it on another platform or with a device that is out of range instead of switched off
- [ ] Add more commands to `util/command_ack.py` once their acknowledgements are verified (eco, graffiti, ...; text, time, speed, joint, freeze behave differently)
- [x] The reply to the set time command is the device info (firmware, screen type, password flag), see `CommonModule.get_device_info` and docs/DEVICE-PROTOCOL.md. Unknown: what byte 6 ("switch status") stands for, it does not follow the screen
- [x] Detect the screen size with `get_device_info` (`DeviceInfo.screen_size`): `IDotMatrixClient(screen_size=None)` asks the device in `connect`. Only tried through the 64x64 reply; the 16x16 and 32x32 types are from the app
- [ ] Add `verify_password` (`07 00 05 02 <p1> <p2> <p3>`, answered by `05 00 05 02 01`) and use the password flag, needs a device with a password to try (setting one can lock the device until it is reset)
- [ ] Make the ack parser accept a different first byte (the app does not check it), after a 32x32 owner confirmed what their device sends.
- [ ] Check on a device whether pacing the upload writes (20 ms, like the app) ends the sporadic "did not acknowledge the upload within 5 seconds" errors. If not: write every packet with response like the app, and capture a debug log
