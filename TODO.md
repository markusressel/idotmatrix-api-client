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
- [ ] CI: add `pytest-cov`, report coverage, add Python 3.14 to matrix

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

- [ ] `Transport` protocol + fake device for tests
- [ ] Opcode table / protocol layer
- [ ] Move `digital_picture_frame.py` out of package top level
- [ ] GIF upload reliability (see TODOs in `gif.py`)
