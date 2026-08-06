# Optional Python API integration

Use the project's reporter abstraction so business logic remains runnable with no RunBuoy
package, no pairing, or an unreachable server. Only a missing top-level `runbuoy` package may
activate the fallback:

```python
from collections.abc import Callable
from typing import Any

try:
    from runbuoy import get_reporter
except ModuleNotFoundError as error:
    if error.name != "runbuoy":
        raise

    class NoopReporter:
        enabled = False

        def progress(
            self,
            current: float,
            total: float,
            *,
            unit: str | None = None,
            phase: str | None = None,
            message: str | None = None,
        ) -> bool:
            return False

        def phase(self, value: str) -> bool:
            return False

        def message(self, value: str) -> bool:
            return False

        def attention(self, value: str, *, status: str = "ACTION_REQUIRED") -> bool:
            return False

    def get_reporter(
        required: bool = False,
        on_error: Callable[[Exception], None] | None = None,
    ) -> NoopReporter:
        del on_error
        if required:
            raise RuntimeError("RunBuoy is not installed")
        return NoopReporter()
```

Do not write `except ImportError` or an unconditional `except ModuleNotFoundError`: that would
hide broken internal RunBuoy dependencies.

Use one reporter instance at the application boundary and inject it into business code:

```python
reporter = get_reporter(required=False, on_error=None)
reporter.phase("Preparing")
accepted_locally = reporter.progress(3, 10, unit="items")
```

`enabled` means a local Worker context was present. A `True` method result means the local Worker
accepted the event; it does not mean the Server or iPhone received it. Best-effort failures return
`False`, disable that reporter, and optionally call `on_error` once. The callback must be
diagnostic only; business execution continues.

Use `required=True` only for strict integration tests or applications that explicitly choose to
make observability mandatory. It raises typed `RunBuoyError` subclasses.
