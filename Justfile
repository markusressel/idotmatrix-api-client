uv_test := "uv run --no-project --python 3.13 --with-editable .. --with pytest --with pytest-asyncio --with pytest-cov --with pytest-mock --with mock --with asyncmock --with textual"

[default]
default:
    @just --list

# run tests (from tests/, like CI); extra args go to pytest
test *args:
    #!/usr/bin/env bash
    set -euxo pipefail
    cd tests
    {{uv_test}} python -m pytest {{args}}

coverage:
    #!/usr/bin/env bash
    set -euxo pipefail
    cd tests
    {{uv_test}} python -m pytest --cov=../idotmatrix --cov-report=term-missing:skip-covered

lint:
    #!/usr/bin/env bash
    set -euxo pipefail
    uvx flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude .venv
    uvx flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics --exclude .venv

build:
    #!/usr/bin/env bash
    poetry build
