---
name: runbuoy
description: Monitor a local command, build, experiment, or agent run on an iPhone through RunBuoy's one-way read-only event path. Use only when the user explicitly invokes $runbuoy and wants safe status, progress, phase, or notification delivery without remote command control.
---

# RunBuoy

Use the installed `runbuoy` CLI. Never create tmux sessions, manage the process, capture
terminal panes, call APNs, or store credentials directly.

## Preflight

Run:

```sh
runbuoy doctor --json
runbuoy capabilities --json
```

Require an installed CLI, pairing, tmux, and a supported platform. Report an unreachable server
clearly; do not weaken sandbox or approval rules to fix it.

## Select progress

Choose only a progress source the command actually exposes:

- Use `structured` when the program already calls the RunBuoy SDK or `runbuoy emit`.
- Use `regex` when stdout contains a stable current/total record.
- Use `lines` when a meaningful bounded unit maps to matching output lines.
- Otherwise use `indeterminate`. Never infer a percentage or ETA from elapsed time.

Read [references/progress.md](references/progress.md) before configuring non-indeterminate
progress. Read [references/privacy.md](references/privacy.md) before sharing a log tail or
constructing a title.

## Start

Generate a short title that identifies the tool and workload without arguments, paths, secrets,
or user input. Then run:

```sh
runbuoy run --json --non-interactive --title "Safe title" --progress indeterminate -- command
```

Preserve the user's exact command after `--`; do not rewrite code to add progress unless asked.
Read [references/cli.md](references/cli.md) for options and local follow-up commands, and
[references/examples.md](references/examples.md) for progress examples.

Return the Run ID and these computer-local commands:

```sh
runbuoy status RUN_ID
runbuoy logs RUN_ID
runbuoy attach RUN_ID
```

`attach`, `logs`, and `cancel` are local-only. Never imply that an iPhone or server can invoke
them. Do not add approval, reply, input, retry, or command actions to a mobile flow.
