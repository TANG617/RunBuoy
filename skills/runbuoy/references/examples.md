# Examples

Long command with honest indeterminate status:

```sh
runbuoy run --json --non-interactive --title "Release build" --progress indeterminate -- make release
```

Python structured progress:

```sh
runbuoy run --json --non-interactive --title "Dataset import" --progress structured -- python import.py
```

Line progress:

```sh
runbuoy run --json --non-interactive --title "100 checks" \
  --progress lines --total 100 --match '^CHECK OK$' -- python checks.py
```

For each detached example, parse `ok`, `detached`, and `worker_ready`; only all three true confirm
handoff. Return the full Run ID, `delivery`, and local `status`, `logs`, `attach`, and `cancel`
commands, then end without polling.

When the user explicitly needs the final target result, add `--wait` instead. Preserve the target
exit code and parse the returned `result`.
