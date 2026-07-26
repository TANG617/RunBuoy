# Progress selection

Structured mode is preferred when instrumentation already exists:

```python
from runbuoy import progress
progress(current=37, total=100, phase="processing", message="Processing item 37")
```

For stable output such as `PROGRESS: 37/100`, use:

```sh
runbuoy run --progress regex --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' -- command
```

For a bounded stream with one matching line per completed item, use:

```sh
runbuoy run --progress lines --total 100 --match '^DONE$' -- command
```

Use indeterminate mode whenever a real current/total measure is unavailable. Do not invent
percentages or an ETA. Reject totals at or below zero.
