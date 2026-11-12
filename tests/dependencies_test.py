import builtins
import io
import subprocess
import sys
from contextlib import redirect_stderr
from pathlib import Path

from tests import TestBase

# what only the terminal UI (the `tui` extra) needs: users of the API client, f.e. the Home Assistant integration, must
# not load any of it
TUI_MODULES = ("textual", "textual_image", "rich", "idotmatrix.tui")

# everything the API client is made of
CLIENT_MODULES = (
    "idotmatrix",
    "idotmatrix.client",
    "idotmatrix.connection_manager",
    "idotmatrix.transport",
    "idotmatrix.protocol",
    "idotmatrix.modules.clock",
    "idotmatrix.modules.gif",
    "idotmatrix.modules.image",
    "idotmatrix.modules.text",
    "idotmatrix.apps.digital_picture_frame",
    "idotmatrix.util.image_utils",
)

REPOSITORY = Path(__file__).resolve().parent.parent


class TestDependencies(TestBase):

    def test_the_api_client_does_not_load_the_terminal_ui(self):
        # GIVEN a fresh interpreter
        code = (
            "import importlib, sys\n"
            f"for name in {CLIENT_MODULES!r}:\n"
            "    importlib.import_module(name)\n"
            f"print(sorted(n for n in sys.modules if n.split('.')[0] in {TUI_MODULES!r} or n.startswith({TUI_MODULES!r})))"
        )

        # WHEN it imports the API client
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                                cwd=REPOSITORY)

        # THEN neither textual nor the terminal UI is loaded
        self.assertEqual("[]", result.stdout.strip())

    def test_the_command_explains_the_missing_extra(self):
        # GIVEN textual is not installed
        from idotmatrix.tui.__main__ import main
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "textual" or name.startswith("textual."):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        saved = {name: module for name, module in sys.modules.items() if name.startswith("idotmatrix.tui.")}
        for name in saved:
            del sys.modules[name]
        builtins.__import__ = fake_import
        stderr = io.StringIO()
        try:
            # WHEN the terminal UI is started
            with redirect_stderr(stderr):
                code = main([])
        finally:
            builtins.__import__ = real_import
            sys.modules.update(saved)

        # THEN it says how to install it
        self.assertEqual(1, code)
        self.assertIn("idotmatrix-api-client[tui]", stderr.getvalue())
