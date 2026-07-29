# CLI reference

Start a run with `runbuoy run [options] -- <argv...>`. The CLI stores complete argv and cwd only
in a local 0600 manifest. It uploads a safe title and structured state events.

Useful options:

- `--title TEXT`: explicit redacted title.
- `--progress structured|lines|regex|indeterminate`.
- `--total NUMBER --match REGEX`: line progress.
- `--pattern REGEX`: current/total regex progress; capture groups 1 and 2 must be numeric.
- `--share-log-tail N`: opt in to 1–100 redacted terminal lines; default is zero.
- `--json --non-interactive`: stable automation output.
- `--dry-run`: preview remotely visible and local-only fields without starting.

`runbuoy list` shows active Runs; `runbuoy list -a` includes completed history. `status`,
`logs`, `attach`, and `cancel` accept unique Run ID prefixes. They inspect the local SQLite
database, files, socket, or tmux server and never wait on a network request.

Use `runbuoy notify --title ... --body ... --level info|success|warning|error` for a one-time
safe message. Use `runbuoy demo notification` or `runbuoy demo live-activity` for built-in
delivery examples.

Pair with `runbuoy device pair`. Configure with `runbuoy config show`,
`runbuoy config set`, and `runbuoy config path`. Install shell completion with
`runbuoy completion install zsh` (or `bash` / `fish`).

Preview local retention cleanup with
`runbuoy history prune --older-than 30d --dry-run`; deletion is permanent and
requires confirmation unless `--yes` is explicitly supplied. Unsynced events
are retained unless `--include-unsynced` is explicitly supplied.
