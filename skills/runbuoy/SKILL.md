---
name: runbuoy
description: Install, diagnose, instrument, start, inspect, notify, or locally control RunBuoy when the user explicitly requests RunBuoy or iPhone status delivery. RunBuoy keeps business execution local-first and remote delivery optional; it never grants remote control.
---

# RunBuoy

Use RunBuoy only when the user explicitly requests it. RunBuoy does not expand permission to
execute, alter, restart, or cancel the underlying task.

## Route the request

- Installation or upgrade: read [references/installation.md](references/installation.md).
- Explicit Python code integration: read [references/python-api.md](references/python-api.md),
  then [references/progress.md](references/progress.md).
- New command: follow **Preflight**, **Start a new Run**, and **Detached handoff** below.
- Existing Run ID: use local `status`, `logs`, `attach`, or `cancel`; do not start a duplicate.
- Existing PID/process not started by RunBuoy: explain that it cannot be adopted or attached.
  Offer a safe one-time `notify`, or restart only with explicit authorization.
- One-time notification: use `runbuoy notify`; if unpaired, only `--dry-run` works and a real
  request returns `not_paired`.
- Diagnosis/delivery recovery: use `doctor`; use `sync` only when the user asks to retry pending
  delivery. `doctor` never syncs.
- Cancellation: `runbuoy cancel RUN_ID --json` is a computer-local request. Never imply that a
  server or iPhone can invoke it.

Ordinary requests such as “run tests” do not authorize RunBuoy installation or instrumentation.
A RunBuoy monitoring request authorizes normal `uv` installation steps described in the
installation reference, but sudo, a system package manager, or a curl installer still requires
confirmation.

## Permanent boundaries

- Use the public `runbuoy` CLI. Do not create tmux sessions, read panes, forge socket/token
  variables, call APNs, or inspect credential storage.
- Preserve the user's exact argv after `--`. Do not modify code to add reporting unless asked.
- Machine → Server → iPhone is one-way and read-only. Never add remote start, cancel, retry,
  approval, input, reply, attach, terminal streaming, polling, SSH, or command queues.
- Read [references/privacy.md](references/privacy.md) before choosing a title, structured
  message, regex/line matching, or `--share-log-tail`.
- Never invent percentage or ETA. Read [references/progress.md](references/progress.md) before
  selecting non-indeterminate progress.

## Preflight

If `command -v runbuoy` fails, follow the global CLI installation route. Then run:

```sh
runbuoy --version
runbuoy doctor --json
runbuoy capabilities --json
```

Require `doctor.local_ready == true`. Delivery is separate:

- `delivery.ready == true`: remote delivery is currently ready, not guaranteed delivered.
- `paired == false`: continue the local Run; no RemoteClient is used and events stay local.
- `paired == true && reachable == false`: continue the local Run; events remain in the outbox.

Never block local execution, logging, status, attach, or cancel because delivery is unavailable.
Report the delivery state plainly. Use `doctor --require-delivery` only when the user explicitly
requires delivery readiness as a separate condition.

## Start a new Run

Choose a short title without arguments, paths, secrets, customer data, or user input. Use
structured only when instrumentation already exists or the user explicitly requested code
changes. Otherwise choose a proven regex/line unit or indeterminate.

Default detached form:

```sh
runbuoy run --json --non-interactive --title "Safe title" \
  --progress indeterminate -- command arg1 arg2
```

Do not add `&`, `nohup`, a terminal keeper, or a separate tmux command. Invalid regex/match
configuration must fail before the target starts.

Use `--wait` only when the user explicitly needs the target's final result in the current turn.
Do not replace `--wait` with status polling.

## Detached handoff

For a non-waiting Run, end the Agent turn only after parsing one successful response with all of:

```text
ok == true
detached == true
worker_ready == true
```

This confirms CLI↔Worker local handoff and target start. It does not confirm Server acceptance or
iPhone delivery. After confirmation, do not poll and do not keep the terminal open. Return the
full Run ID, current `delivery`, and the computer-local commands in `local` (`status`, `logs`,
`attach`, `cancel`), then exit.

If handoff fails, do not blindly retry: the Run is marked `LOST` before ACK so a user/Agent retry
cannot silently duplicate the target. Report the structured error and ask before restarting.
