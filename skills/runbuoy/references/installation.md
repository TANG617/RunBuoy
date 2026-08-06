# Installation routing

## Global CLI

First check:

```sh
command -v runbuoy
```

If missing and `uv` is available, an explicit RunBuoy request authorizes:

```sh
uv tool install --python 3.12 runbuoy
```

Then verify:

```sh
runbuoy --version
runbuoy doctor --json
runbuoy capabilities --json
```

If `uv` itself is absent, or tmux needs installation, consult
`docs/user-guide/installation.md`. Ask before using sudo, a system package manager, or a curl
installer. Do not weaken sandbox or approval rules. macOS/Linux, Python 3.12+, and tmux are the
supported local runtime.

## Project Python API

Only install the project API when the user explicitly asks for instrumentation/code changes.
Use the project's actual interpreter (for example `uv run python`, `.venv/bin/python`, or the
declared runtime), not whichever `python` happens to be global. Check import with that interpreter.

For PEP 621/uv projects, keep RunBuoy out of default business dependencies:

```sh
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

This creates an optional extra named `runbuoy`. For requirements-based projects, create a
separate `requirements-runbuoy.txt` containing `runbuoy`; do not add it to the default
requirements file.

Global CLI and project API environments are intentionally separate. Install both when both are
needed. If the project's Python range is incompatible with Python 3.12+, do not change it without
the user's decision.
