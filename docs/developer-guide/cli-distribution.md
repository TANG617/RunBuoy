# CLI distribution and PyPI releases

The RunBuoy CLI is published as the
[`runbuoy`](https://pypi.org/project/runbuoy/) project on PyPI. PyPI is the
canonical package registry; `uv tool` and `pipx` install the same wheel into
isolated Python environments and expose the `runbuoy` executable on `PATH`.

The initial public release is `0.1.0`, published from the
[`cli-v0.1.0`](https://github.com/TANG617/RunBuoy/tree/cli-v0.1.0)
tag through the
[`Publish CLI`](https://github.com/TANG617/RunBuoy/actions/workflows/publish-cli.yml)
GitHub Actions workflow.

## User installation

RunBuoy supports macOS and Linux and requires Python 3.12 or newer. Durable
runs also require the system `tmux` executable; Python package managers cannot
install this operating-system dependency.

Install `tmux` first:

```bash
# macOS
brew install tmux

# Debian or Ubuntu
sudo apt install tmux
```

Install RunBuoy with `uv`:

```bash
uv tool install runbuoy
runbuoy doctor
```

Or install it with `pipx`:

```bash
pipx install runbuoy
runbuoy doctor
```

If the executable directory is not yet on `PATH`, run the matching setup
command and restart the shell:

```bash
uv tool update-shell
# or
pipx ensurepath
```

Upgrade or remove RunBuoy with the tool originally used to install it:

```bash
uv tool upgrade runbuoy
uv tool uninstall runbuoy

pipx upgrade runbuoy
pipx uninstall runbuoy
```

To select an exact release:

```bash
uv tool install 'runbuoy==0.1.2'
pipx install 'runbuoy==0.1.2'
```

## Package layout

The publishable Python project lives entirely under `cli`:

- `cli/pyproject.toml` contains package metadata, dependencies, the Hatchling
  build configuration, and the console entry point.
- `cli/src/runbuoy/__init__.py` is the single source for the package version.
- `cli/README.md` becomes the PyPI project description.
- `cli/LICENSE` is included in the wheel and source distribution.
- `cli/uv.lock` locks the development and test environment.

The executable is declared as:

```toml
[project.scripts]
runbuoy = "runbuoy.cli.app:main"
```

Hatchling reads the release version from the package:

```toml
[project]
dynamic = ["version"]

[tool.hatch.version]
path = "src/runbuoy/__init__.py"
```

The current package is pure Python and produces a universal
`py3-none-any.whl`. Runtime support remains limited to macOS and Linux because
the CLI relies on `tmux`, Unix sockets, PTYs, and POSIX process groups.

## Local package validation

Run the CLI quality checks before preparing a release:

```bash
cd cli
uv sync --all-groups --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

Build and validate the exact artifacts that PyPI will receive:

```bash
uv build --clear --no-sources
uvx --from twine twine check dist/*
```

The build must produce both files:

```text
runbuoy-X.Y.Z-py3-none-any.whl
runbuoy-X.Y.Z.tar.gz
```

Inspect the wheel when changing packaging rules:

```bash
unzip -l dist/runbuoy-X.Y.Z-py3-none-any.whl
unzip -p dist/runbuoy-X.Y.Z-py3-none-any.whl '*/METADATA'
```

Confirm that the wheel contains the `runbuoy` package, console entry point,
README-derived description, MIT license, dependency metadata, project URLs,
and the intended `Requires-Python` value.

## Trusted Publishing configuration

RunBuoy uses PyPI Trusted Publishing rather than a long-lived PyPI API token.
The PyPI publisher identity must exactly match:

```text
PyPI project: runbuoy
GitHub owner: TANG617
GitHub repository: RunBuoy
Workflow filename: publish-cli.yml
GitHub environment: pypi
```

The GitHub `pypi` environment requires an explicit deployment approval. The
publish job receives only `id-token: write`, while the workflow-level default
is `contents: read`. The temporary OIDC credential is issued only after the
build job and environment protection rules succeed.

If the repository, workflow filename, or environment name changes, update the
PyPI Trusted Publisher before attempting another release. A mismatch causes
the publish action to fail with an `invalid-publisher` error.

Never add `PYPI_API_TOKEN`, a PyPI password, or other long-lived publishing
credentials to GitHub secrets or the repository.

## Release procedure

PyPI release files are immutable. Never reuse a version that has already been
published.

1. Update `__version__` in `cli/src/runbuoy/__init__.py` using semantic
   versioning.
2. Update the changelog or user-facing documentation for the release.
3. Run all local validation commands above.
4. Open and merge a pull request so the release commit and publishing
   workflow are present on `main`.
5. Update local `main` and create an annotated tag whose version exactly
   matches `__version__`.

For example, to publish `0.1.2`:

```bash
git switch main
git pull --ff-only
git tag -a cli-v0.1.2 -m "RunBuoy CLI 0.1.2"
git push origin refs/tags/cli-v0.1.2
```

The tag triggers `.github/workflows/publish-cli.yml`. The workflow:

1. verifies that `cli-vX.Y.Z` exactly matches the package version;
2. runs the CLI test suite;
3. builds the wheel and source distribution;
4. validates their metadata with Twine;
5. installs the wheel and runs `runbuoy doctor`;
6. uploads the artifacts between isolated jobs;
7. waits for approval of the `pypi` environment;
8. exchanges GitHub's OIDC identity for a short-lived PyPI credential; and
9. publishes the artifacts and their attestations.

Review and approve the deployment from the workflow run only after the build
job is green.

## Post-release verification

First verify the public PyPI metadata:

```bash
curl --fail --silent --show-error \
  https://pypi.org/pypi/runbuoy/json |
  jq '.info | {name, version, requires_python, project_url}'
```

Then test both supported installation paths from the public index in isolated
directories:

```bash
VERSION=0.1.2
VERIFY_ROOT="$(mktemp -d)"
VERIFY_PYTHON="$(uv python find 3.12)"

UV_TOOL_DIR="$VERIFY_ROOT/uv-tools" \
UV_TOOL_BIN_DIR="$VERIFY_ROOT/uv-bin" \
uv tool install --refresh-package runbuoy "runbuoy==$VERSION"

RUNBUOY_HOME="$VERIFY_ROOT/uv-home" \
RUNBUOY_DISABLE_KEYRING=1 \
"$VERIFY_ROOT/uv-bin/runbuoy" doctor --json

PIPX_HOME="$VERIFY_ROOT/pipx-home" \
PIPX_BIN_DIR="$VERIFY_ROOT/pipx-bin" \
uvx pipx install --python "$VERIFY_PYTHON" "runbuoy==$VERSION"

RUNBUOY_HOME="$VERIFY_ROOT/pipx-runbuoy-home" \
RUNBUOY_DISABLE_KEYRING=1 \
"$VERIFY_ROOT/pipx-bin/runbuoy" doctor --json
```

Both `doctor` results must report the expected `cli_version`, supported
Python/platform checks, an available `tmux`, and `"ok": true`. Pairing and
server reachability are not required to prove that package installation
succeeded.

## Failed or compromised releases

- If validation fails before publishing, fix the problem and prepare a new
  commit. Do not publish an artifact that differs from the reviewed build.
- If PyPI already accepted a version, increment the version for every fix;
  PyPI does not allow replacing its files.
- If a release should no longer be selected by installers, yank it from the
  PyPI project and document the replacement version. Yanking does not delete
  the release.
- If the Trusted Publisher configuration is suspected of compromise, remove
  or replace it in PyPI, review the GitHub environment and workflow history,
  and do not create another release tag until the publishing boundary is
  restored.
