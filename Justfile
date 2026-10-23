uv_test := "uv run --no-project --python 3.13 --with-editable .. --with pytest --with pytest-asyncio --with pytest-cov --with pytest-xdist --with pytest-mock --with mock --with asyncmock --with textual --with textual-image"

[default]
default:
    @just --list

# run tests in parallel (from tests/, like CI); extra args go to pytest and run them in one process
test *args:
    #!/usr/bin/env bash
    set -euxo pipefail
    cd tests
    {{uv_test}} python -m pytest {{ if args == "" { "-n auto" } else { "" } }} {{args}}

# run the terminal UI, extra args go to it, f.e. `just tui ~/pictures --choose`
tui *args:
    uv run --no-project --python 3.13 --with-editable . --with textual --with textual-image python -m idotmatrix.tui {{args}}

coverage:
    #!/usr/bin/env bash
    set -euxo pipefail
    cd tests
    {{uv_test}} python -m pytest -n auto --cov=../idotmatrix --cov-report=term-missing:skip-covered

lint:
    #!/usr/bin/env bash
    set -euxo pipefail
    uvx flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude .venv
    uvx flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics --exclude .venv

build:
    #!/usr/bin/env bash
    poetry build
