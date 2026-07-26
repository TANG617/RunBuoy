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

Return the Run ID and local `status`, `logs`, and `attach` commands printed in the JSON result.
