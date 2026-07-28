# Development

## Prerequisites

- Python 3.12+ managed with `uv`
- tmux on macOS or Linux
- Docker for PostgreSQL integration/E2E
- Xcode on macOS for iOS builds and tests

## Protocol and security

```bash
uv sync --group dev
uv run pytest packages/protocol/tests
uv run python scripts/check_read_only_boundary.py
uvx openapi-spec-validator packages/protocol/openapi.yaml
```

## CLI

```bash
cd cli
uv sync --all-groups
uv run ruff check .
uv run mypy src
uv run pytest
```

Package construction, isolated-install checks, and PyPI release steps are in
[`cli-distribution.md`](cli-distribution.md).

## Server

```bash
cd server
uv sync --all-groups
uv run alembic upgrade head
uv run ruff check .
uv run mypy app worker
uv run pytest
```

Server tests use isolated configuration and mock APNs. PostgreSQL parity and
E2E run in Docker/GitHub Actions.

## iOS

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

The smoke environment uses PostgreSQL plus `APNS_MODE=mock`; it verifies
pairing, long/short Runs, push lifecycle payloads, read projections, and the
absence of remote-control routes.
