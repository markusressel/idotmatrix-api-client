from pathlib import Path
from unittest import IsolatedAsyncioTestCase


def _find_test_folder() -> Path:
    p = Path("./")

    if p.absolute().parts[-1] == "tests":
        return p
    else:
        import glob
        while str(p.absolute()) != "/":
            files = glob.glob(str(Path(p)) + '/**/tests', recursive=True)
            if len(files) > 0:
                return Path(files[0]).absolute()
            else:
                p = p.parent.absolute()

    raise AssertionError("test folder not found")


class TestBase(IsolatedAsyncioTestCase):
    _test_folder = _find_test_folder()
