# CLI reference

`runbuoy run [options] -- <argv...>` stores complete argv and cwd only in a local mode-0600
manifest. Local events commit before any optional upload.

Useful options:

- `--title TEXT`: explicit sanitized title.
- `--progress structured|lines|regex|indeterminate`.
- `--total NUMBER --match REGEX`: bounded line progress.
- `--pattern REGEX`: current/total regex progress; groups 1 and 2 must be numeric.
- `--share-log-tail N`: explicitly share 1–100 sanitized terminal lines; default zero.
- `--json --non-interactive`: stable automation output.
- `--wait`: wait for the real target result and preserve its exit code.
- `--dry-run`: validate and preview fields without starting a Run.

The default detached response confirms a two-phase local handoff and contains `detached`,
`worker_ready`, `delivery`, and local follow-up commands. `status` may already be terminal for an
instant task.

Local Run commands:

```sh
runbuoy list --json
runbuoy status RUN_ID --json
runbuoy logs RUN_ID
runbuoy attach RUN_ID
runbuoy cancel RUN_ID --json
```

These use local database/files/socket/tmux state. Pairing and server reachability are not
prerequisites. Preserve full IDs in automation; prefixes and `@latest`/`@active` are interactive
conveniences.

Delivery commands:

```sh
runbuoy doctor --json
runbuoy doctor --require-delivery --json
runbuoy sync --json
runbuoy notify --title "Safe title" --body "Safe body" --json
```

`sync` retries retained events for every Run under one machine-wide outbox lease. It requires
pairing. `notify --dry-run` works unpaired; a real unpaired notification returns `not_paired`.
Server acceptance is not iPhone delivery.
