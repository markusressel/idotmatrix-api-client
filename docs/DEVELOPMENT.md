# Development

## Setup

Python 3.12 to 3.14 and [Poetry](https://python-poetry.org/) are needed.

```sh
git clone https://github.com/markusressel/idotmatrix-api-client.git
cd idotmatrix-api-client/
poetry install --with test
```

Add `--extras tui` to work on the terminal UI. Its tests that need textual are skipped without it.

## Commands

[`just`](https://github.com/casey/just) runs the common tasks (`make <target>` proxies to `just <target>`):

```sh
just test       # all tests, extra arguments go to pytest
just test-core  # the tests without textual (the `tui` extra), like the main CI job
just coverage   # line coverage with missing lines
just lint       # the same flake8 checks as CI
just build      # poetry build
just tui        # run the terminal UI, extra arguments go to it
```

Without `just`, run `cd tests && pytest`. The tests need no hardware or Bluetooth.

## Further reading

- [AGENTS.md](../AGENTS.md): layout, conventions and testing rules of the code base
- [DEVICE-PROTOCOL.md](DEVICE-PROTOCOL.md): what is known about the devices
