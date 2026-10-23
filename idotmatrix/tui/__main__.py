import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="idotmatrix-tui",
        description="Pick pictures and animations in a terminal and show them on an iDotMatrix display.")
    parser.add_argument("folder", nargs="?", type=Path, help="the folder to open (default: the last one)")
    parser.add_argument("--address", help="Bluetooth address of the display (default: the last one, or search)")
    args = parser.parse_args(argv)
    try:
        from idotmatrix.tui.app import IDotMatrixApp
    except ImportError as e:
        print(f"The terminal UI needs textual: pip install 'idotmatrix-api-client[tui]' ({e})", file=sys.stderr)
        return 1
    folder = args.folder.expanduser().resolve() if args.folder else None
    if folder is not None and not folder.is_dir():
        print(f"{folder} is not a folder", file=sys.stderr)
        return 1
    IDotMatrixApp(folder=folder, address=args.address).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
