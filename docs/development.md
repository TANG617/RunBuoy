# Development

## Prerequisites

- Python 3.12+ managed with `uv`
- tmux on macOS or Linux
- Docker for PostgreSQL integration/E2E
- Xcode on macOS for iOS builds and tests

Before changing code, follow the [source code reading guide](source-reading-guide.md).
It traces one Run from `runbuoy run` through the Worker, local queue, Server
projection, APNs outbox, Read API, and native iOS presentation. It also marks the
current implementation differences from ADR 0002.

## Protocol and security

```bash
uv sync --group dev
uv run pytest packages/protocol/tests
uv run python scripts/check_read_only_boundary.py
uvx openapi-spec-validator packages/protocol/openapi.yaml
```

The accepted protocol is latest-state-wins eventual consistency. New work must
preserve these invariants:

- revision gaps are legal;
- stale state is acknowledged and must not poison retries;
- progress never regresses;
- replaceable state may be coalesced;
- terminal snapshots remain durable until acknowledged;
- network silence never becomes execution failure.

See [ADR 0002](adr/0002-eventual-consistency-and-network-tolerance.md).

## CLI

```bash
cd cli
uv sync --all-groups
uv run ruff check .
uv run mypy src
uv run pytest
```

## Server

```bash
cd server
uv sync --all-groups
uv run alembic upgrade head
uv run ruff check .
uv run mypy app worker
uv run pytest
```

Server tests use isolated configuration and mock APNs. PostgreSQL parity and E2E
run in Docker/GitHub Actions.

## iOS

The product compatibility baseline is iOS 18. iOS 26 APIs are optional visual
enhancements and must be guarded with availability checks and iOS 18 fallbacks.
The current visual implementation still targets iOS 26; restoring the iOS 18
build is an accepted implementation follow-up rather than a product-scope
change.

Current project build command:

```bash
xcodebuild \
  -project apps/ios/RunBuoy.xcodeproj \
  -scheme RunBuoy \
  -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO \
  build
```

Simulator unit tests run only where an installed Xcode runtime is available.
Signing and real APNs require external Apple configuration.

## E2E

```bash
./scripts/e2e_smoke.sh
```

The smoke environment uses PostgreSQL plus `APNS_MODE=mock`; it verifies pairing,
long/short Runs, push lifecycle payloads, read projections, and the absence of
remote-control routes.

The next network-tolerance scenarios should cover dropped replaceable updates,
duplicate and reordered revisions, stale acknowledgements, long disconnects,
missing heartbeat without execution transition, explicit terminal convergence,
and APNs loss followed by Read API convergence.
