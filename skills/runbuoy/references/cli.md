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

Local commands are `list`, `status`, `logs`, `attach`, and `cancel`. They inspect the local
SQLite database, files, socket, or tmux server. They are never remote API actions.

Use `runbuoy notify --title ... --body ... --level info|success|warning|error` for a one-time
safe message.
