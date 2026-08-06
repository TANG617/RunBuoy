---
description: Install, verify, upgrade, and remove the RunBuoy CLI on macOS or Linux, with optional Python API setup for project environments.
---

# Install the CLI

The RunBuoy CLI is published on [PyPI](https://pypi.org/project/runbuoy/). It supports macOS and Linux and requires Python 3.12 or newer. Manual installation is available now; the one-click installer has not been released.

## System dependency

Durable Runs require the system-provided `tmux`:

```bash
# macOS
brew install tmux

# Debian / Ubuntu
sudo apt update
sudo apt install tmux

# Fedora
sudo dnf install tmux

# Arch Linux
sudo pacman -S tmux
```

Python package managers do not install this system dependency.

## Install with uv (recommended)

On macOS, you can run `brew install uv`. On Linux or without Homebrew, use uv's official installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv tool update-shell
```

Restart the terminal, then install and verify the CLI:

```bash
uv tool install --python 3.12 runbuoy
runbuoy --version
runbuoy doctor
runbuoy capabilities --json
```

Upgrade or remove it:

```bash
uv tool upgrade runbuoy
uv tool uninstall runbuoy
```

## Install with pipx

If uv is unavailable, pipx is a supported alternative for the global CLI:

```bash
pipx install runbuoy
pipx ensurepath
runbuoy --version
runbuoy doctor
```

Upgrade or remove it:

```bash
pipx upgrade runbuoy
pipx uninstall runbuoy
```

## Install a specific version

Replace `X.Y.Z` with the required version:

```bash
uv tool install --python 3.12 'runbuoy==X.Y.Z'
# or
pipx install 'runbuoy==X.Y.Z'
```

## Shell completion

Choose your current shell explicitly:

```bash
runbuoy completion install bash
runbuoy completion install zsh
runbuoy completion install fish
```

Run only one of these commands. Restart the terminal afterward to complete commands, options, valid enum values, and local Run IDs.

## Optional: project Python API

`uv tool install` creates an isolated environment for the global CLI. It does not make the package importable by your project. Declare it separately in the directory that contains `pyproject.toml`:

```bash
cd my-project
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

Update the project dependency:

```bash
uv lock --upgrade-package runbuoy
uv sync --extra runbuoy
```

Remove it from the project:

```bash
uv remove --optional runbuoy runbuoy
```

SDK calls such as `progress()` must run inside the target process tree started by RunBuoy. If you cannot change project dependencies, use `runbuoy emit` from the target process instead; see [Progress modes](/en/guide/progress).

## Troubleshooting

- Command not found: run `uv tool update-shell` or `pipx ensurepath`, then restart the terminal.
- `doctor` reports missing tmux: install it with the operating system package manager above, not pip.
- `local_ready=true` but `delivery.ready=false`: local execution remains ready; pairing or Server reachability is unavailable, so events stay in the local outbox.
- Project API cannot be installed: ensure the project `requires-python` includes Python 3.12+. An installer should not silently broaden the project's supported Python range.

Removing the distribution does not delete local configuration, credentials, Run history, or logs. To clean up history, use the protected `runbuoy history prune` command before uninstalling; do not recursively delete an unknown directory.
