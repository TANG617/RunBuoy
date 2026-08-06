---
description: Run commands, send notifications, inspect local status, and explicitly control optional log sharing with RunBuoy.
---

# Runs and notifications

## Run a command

Put the complete original command after `--`:

```bash
runbuoy run -- python3 experiment.py
```

RunBuoy preserves the original exit code, mirrors output locally, and optionally sends a safe status projection. A normal detached start returns after the Worker-ready nonce/Socket ACK and `run.started` handoff; the caller can then exit. To wait and receive the original command’s exit code:

```bash
runbuoy run --wait -- command
```

Provide a title that contains no paths, arguments, or sensitive information:

```bash
runbuoy run \
  --title "Gurobi experiment" \
  -- python3 experiment.py
```

## Send a one-time notification

You can send a status notification without starting a managed Run:

```bash
runbuoy notify \
  --title "Build completed" \
  --body "Release build succeeded" \
  --level success
```

Built-in demos require no arguments:

```bash
runbuoy demo notification
runbuoy demo live-activity
```

## Local commands

These commands run on the current computer:

```bash
runbuoy list
runbuoy list -a
runbuoy status RUN_ID
runbuoy logs RUN_ID
runbuoy attach RUN_ID
runbuoy cancel RUN_ID
```

Neither the iPhone nor the server can invoke them.

These local commands remain available without pairing and while the Server is unreachable. Pending events can be retried later with `runbuoy sync --json`.

`list` shows active Runs by default; `-a/--all` includes completed history. Times use the local time zone and include seconds. `status`, `logs`, `attach`, and `cancel` accept a unique Run ID prefix; `@latest` selects the most recent Run.

Preview and prune older local records and logs:

```bash
runbuoy history prune --older-than 30d --dry-run
runbuoy history prune --older-than 30d
```

Pruning asks for confirmation and cannot be undone. Runs with unsynchronized events are kept unless `--include-unsynced` is explicitly provided.

## Preview remote data

Inspect what would be visible remotely without starting a command:

```bash
runbuoy run --dry-run --title "Safe title" -- command --secret local-only
runbuoy notify --dry-run --title "Preview" --body "Nothing is sent"
```

## Optional safe log snippet

Full logs always stay local. When needed, explicitly upload up to 100 redacted trailing lines:

```bash
runbuoy run --share-log-tail 20 -- command
```

The iOS app clearly labels the uploaded snippet, and the server retains it for at most 24 hours.
