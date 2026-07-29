# Install the CLI

The RunBuoy CLI is published on [PyPI](https://pypi.org/project/runbuoy/). It supports macOS and Linux and requires Python 3.12 or newer.

## Install with uv

```bash
uv tool install runbuoy
runbuoy doctor
```

If your terminal still cannot find `runbuoy`:

```bash
uv tool update-shell
```

Upgrade or remove it:

```bash
uv tool upgrade runbuoy
uv tool uninstall runbuoy
```

## Install with pipx

```bash
pipx install runbuoy
runbuoy doctor
```

If your terminal still cannot find `runbuoy`:

```bash
pipx ensurepath
```

Upgrade or remove it:

```bash
pipx upgrade runbuoy
pipx uninstall runbuoy
```

## Install a specific version

```bash
uv tool install 'runbuoy==0.1.2'
# or
pipx install 'runbuoy==0.1.2'
```

## Install tmux

Durable runs require the system-provided `tmux`:

```bash
# macOS
brew install tmux

# Debian / Ubuntu
sudo apt install tmux
```

Python package managers do not install this system dependency.

## Shell completion

Choose your current shell explicitly:

```bash
runbuoy completion install zsh
# or
runbuoy completion install bash
runbuoy completion install fish
```

Restart the terminal afterward. Commands, options, valid enum values, and local Run IDs will be completed automatically. `status` and `logs` include every local Run; `attach` and `cancel` include only active Runs.
