# RunBuoy CLI

RunBuoy keeps long-running commands visible from an iPhone without exposing a
remote-control surface. The CLI runs commands locally, records structured
status and progress, and sends a deliberately limited projection to a paired
RunBuoy server.

## Requirements

- macOS or Linux
- Python 3.12 or newer
- `tmux` for durable runs

Install `tmux` before RunBuoy:

```bash
# macOS
brew install tmux

# Debian or Ubuntu
sudo apt install tmux
```

## Install

Install the CLI in an isolated environment with
[uv](https://docs.astral.sh/uv/):

```bash
uv tool install runbuoy
runbuoy completion install zsh  # or bash / fish
```

Or use [pipx](https://pipx.pypa.io/):

```bash
pipx install runbuoy
```

The installed executable is available directly:

```bash
runbuoy doctor
runbuoy capabilities --json
```

New installations use `https://api.runbuoy.cloud` as the default server URL.
Override it when needed with
`runbuoy config set --server-url <url>`.

Upgrade with the same tool used for installation:

```bash
uv tool upgrade runbuoy
# or
pipx upgrade runbuoy
```

## Quick start

Pair this machine with the RunBuoy iOS app:

```bash
runbuoy device pair
```

Verify delivery with built-in examples:

```bash
runbuoy demo notification
runbuoy demo live-activity
```

Run a command:

```bash
runbuoy run -- python3 experiment.py
```

`runbuoy list` shows active Runs. Use `runbuoy list -a` to include completed
history. Run IDs may be supplied as unique prefixes, or as `@latest`.
Preview old local history before permanently pruning it with:

```bash
runbuoy history prune --older-than 30d --dry-run
```

Send a notification without starting a managed run:

```bash
runbuoy notify \
  --title "Build completed" \
  --body "Release build succeeded" \
  --level success
```

RunBuoy does not upload full command arguments, working directories,
environment variables, source code, or complete logs by default. See the
[security documentation](https://github.com/TANG617/RunBuoy/blob/main/docs/security.md)
for the complete data boundary.

## Source and support

Source code, documentation, and issue tracking are available in the
[RunBuoy repository](https://github.com/TANG617/RunBuoy).
Maintainer packaging and release instructions are in
[`docs/cli-distribution.md`](https://github.com/TANG617/RunBuoy/blob/main/docs/cli-distribution.md).

RunBuoy is licensed under the MIT License.
