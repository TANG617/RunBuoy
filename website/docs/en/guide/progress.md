# Progress modes

RunBuoy displays only progress reported by the command. It never estimates a percentage or ETA from elapsed time.

## Structured progress

Your program can report progress through the Python SDK:

```python
from runbuoy import progress

progress(
    current=37,
    total=100,
    phase="processing",
    message="Processing item 37",
)
```

A child process can emit the same event:

```bash
runbuoy emit progress \
  --current 37 \
  --total 100 \
  --phase processing \
  --message "Processing item 37"
```

## Line progress

Use line matching when each matching line represents one bounded unit of work:

```bash
runbuoy run \
  --progress lines \
  --total 100 \
  --match '^Hello World$' \
  -- python3 script.py
```

## Regex progress

Use a regex when output contains stable current and total values:

```bash
runbuoy run \
  --progress regex \
  --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' \
  -- python3 experiment.py
```

## Indeterminate progress

When there is no honest progress source, omit the progress options. The iPhone shows the run status, phase, elapsed time, and last update instead of inventing a percentage.
