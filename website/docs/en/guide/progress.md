---
description: Report honest progress to RunBuoy with the Python SDK, runbuoy emit, line matching, or regular expressions.
---

# Progress modes

RunBuoy displays only progress reported by the command. It never estimates a percentage or ETA from elapsed time.

## Structured progress

The CLI environment created by `uv tool` is isolated from your project environment. Before using the Python SDK, declare it in the project root:

```bash
uv add --optional runbuoy runbuoy
uv sync --extra runbuoy
```

Then call the API from your program:

```python
from runbuoy import get_reporter

reporter = get_reporter()
reporter.progress(
    current=37,
    total=100,
    phase="processing",
    message="Processing item 37",
)
```

These calls must run inside the target process tree started by RunBuoy so they can use the local Socket and temporary Token injected by the Worker:

```bash
runbuoy run --progress structured -- uv run --extra runbuoy python experiment.py
```

If you cannot change project dependencies, emit the equivalent event from a child process started by RunBuoy:

```bash
runbuoy emit progress \
  --current 37 \
  --total 100 \
  --phase processing \
  --message "Processing item 37"
```

Reporter methods are best-effort and return `False` when RunBuoy context is absent or the local Worker fails; business execution continues. A `True` result confirms only local Worker acceptance, not Server or iPhone delivery.

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

Records accepted by line/regex matching become the latest sanitized message and may be visible remotely. Structured phase, message, attention, and explicit log tails may also be remote; sanitization is not permission to disclose sensitive output.

## Indeterminate progress

When there is no honest progress source, omit the progress options. The iPhone shows indeterminate progress and Machine-confirmed elapsed time instead of inventing a percentage. The elapsed value advances only when a new event or heartbeat reaches the Live Activity, so a frozen value indicates that the delivery or display path has not received a fresh confirmation.
