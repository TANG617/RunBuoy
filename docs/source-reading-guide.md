# RunBuoy source code reading guide

This guide explains the current repository by following one Run from the shell to
the iPhone. It is intentionally organized by execution flow rather than by
language or directory.

## 1. Start with the product invariants

Read these files first:

1. [`docs/PRD.md`](PRD.md) — product requirements, network-tolerance semantics,
   iOS 18 compatibility, and acceptance criteria.
2. [`docs/adr/0001-one-way-read-only-architecture.md`](adr/0001-one-way-read-only-architecture.md)
   — why the phone cannot control the Machine.
3. [`docs/adr/0002-eventual-consistency-and-network-tolerance.md`](adr/0002-eventual-consistency-and-network-tolerance.md)
   — why newest state wins, intermediate state may be dropped, and network
   silence is not failure.
4. [`docs/architecture.md`](architecture.md) — the four planes and their trust
   boundaries.
5. [`docs/protocol.md`](protocol.md) — Run states, revisions, progress, and
   delivery classes.

Keep two questions in mind while reading all code:

```text
Is this local execution truth, synchronized projection, or presentation?
Is this data replaceable state or a durable milestone?
```

## 2. Repository map

```text
cli/                         Machine-side CLI, Worker, tmux, SQLite, progress
server/                      FastAPI, PostgreSQL projection, outbox, APNs
apps/ios/                    Native read-only SwiftUI app and Live Activity
packages/protocol/           Shared JSON/OpenAPI contracts and fixtures
packages/sdk-python/         Structured progress helper for Python programs
scripts/                     E2E and architecture-boundary checks
skills/runbuoy/              Explicit Codex Skill
infra/                       Docker Compose development deployment
docs/                        Product, architecture, security, and operations
```

The old inherited rzr/Expo files may still be visible in Git history or legacy
paths, but they are not the intended RunBuoy runtime. The active product path is
`cli/ + server/ + apps/ios/`.

## 3. First reading pass: trace `runbuoy run`

### Step 1 — CLI entry point

Open:

```text
cli/src/runbuoy/cli/app.py
```

Start at:

```python
run_command(...)
```

Follow these operations in order:

1. validates progress options;
2. creates a Run ID;
3. derives a safe display title;
4. builds a local `RunManifest` containing the real argv and cwd;
5. writes the manifest with restrictive permissions;
6. creates the local Run and first event in SQLite;
7. asks `TmuxExecutor` to start the Worker;
8. reports only safe local commands and the Run ID;
9. attempts a best-effort initial synchronization.

Important distinction:

```text
RunManifest argv/cwd        local and sensitive
Run title/state/progress    eligible for safe synchronization
```

Next read:

```text
cli/src/runbuoy/models.py
cli/src/runbuoy/security/titles.py
cli/src/runbuoy/security/redaction.py
```

`RunManifest` is the local execution specification. `RunEvent` is the current
wire-shaped state record. `Progress.determinate()` clamps progress and computes
the fraction.

### Step 2 — tmux only owns persistence

Open:

```text
cli/src/runbuoy/executors/tmux.py
```

Read `TmuxExecutor.start()`.

The important command shape is:

```text
tmux
└── python -m runbuoy _worker --manifest <local-path>
```

The target command is not directly interpolated into a shell string. It remains
inside the protected manifest. tmux provides background persistence and local
attach; it does not determine progress or task success.

### Step 3 — Worker and target process

Open:

```text
cli/src/runbuoy/worker/runtime.py
```

Read in this order:

1. `Worker.run()`
2. `Worker._run_target()`
3. `Worker.emit()`
4. `Worker._upload_loop()`
5. `Worker.socket_handler()`
6. `_safe_log_tail()`

The target structure is:

```text
tmux session
└── runbuoy Worker
    ├── local Unix event socket
    ├── PTY
    ├── independent target process group
    ├── local log
    ├── local SQLite synchronization queue
    └── target command
```

Key behaviors to understand:

- `pty.openpty()` creates a terminal-compatible stream.
- `start_new_session=True` gives the target a process group that local cancel can
  signal safely.
- output is copied to the tmux pane, local log, and progress adapter.
- `RUNBUOY_EVENT_SOCKET` and `RUNBUOY_EVENT_TOKEN` let the child emit structured
  state without receiving the Server credential.
- the final result is written atomically to `result.json`.
- full output stays local unless a bounded safe tail is explicitly requested.

Then read:

```text
cli/src/runbuoy/worker/socket_server.py
cli/src/runbuoy/worker/signals.py
cli/src/runbuoy/progress/adapters.py
```

These explain local structured updates, local-only cancellation, line/regex
parsing, ANSI/chunk handling, and signal escalation.

## 4. Second reading pass: local durability and upload

### Step 4 — SQLite synchronization state

Open:

```text
cli/src/runbuoy/persistence/store.py
```

Read:

1. `_initialize()` — local tables and indices;
2. `create_run()` — Run creation and initial state;
3. `append_event()` / `_append_event_in_transaction()` — revision assignment and
   local snapshot update;
4. `pending_events()` — selection for upload;
5. `mark_delivered()` / `mark_failed()` — retry bookkeeping.

The current implementation stores an event row for each update. The accepted
product direction in ADR 0002 is to evolve this toward two behaviors:

```text
replaceable state    coalesce to newest pending value
terminal milestone   retain until acknowledged
```

Do not assume the current strict row-by-row behavior is the final protocol.

### Step 5 — HTTP synchronization

Open:

```text
cli/src/runbuoy/networking/client.py
```

Read:

1. `RemoteClient.upsert_run()`
2. `RemoteClient.upload_events()`
3. `flush_pending()`

`flush_pending()` groups pending records by Run, initializes the remote Run when
needed, uploads a batch, and marks acknowledged rows delivered.

Current-versus-target warning:

- current code treats non-2xx responses as upload failures;
- current Server rejects an older sequence with HTTP 409;
- ADR 0002 requires stale updates to be acknowledged as `ignored_stale`, removed
  from the queue, and never retried forever;
- revision gaps must be legal;
- final snapshots must converge without a complete intermediate history.

This is the most important implementation area for the next reliability PR.

## 5. Third reading pass: Server ingest and projection

### Step 6 — Server composition and authorization

Open:

```text
server/app/main.py
server/app/auth.py
server/app/api.py
```

`main.py` is deliberately small: it creates FastAPI, validates settings, and
installs the `/v1` router.

In `auth.py`, compare `DEVICE_SCOPES` and `MACHINE_SCOPES`. Their non-overlap is
how the code enforces the one-way product boundary:

```text
Machine credential    creates Runs and writes state
Device credential     reads projection and registers its own tokens
```

In `api.py`, first read only these endpoint families:

```text
/devices/bootstrap
/pairing-sessions
/runs/{id}
/runs/{id}/events:batch
/runs
/machines
/notifications
/live-activities
```

Ignore webhooks on the first pass; they use the same projection path later.

### Step 7 — Database model

Open:

```text
server/app/models.py
server/migrations/versions/0001_initial.py
```

Focus on:

```text
Device
Machine
MachineDeviceSubscription
Run
RunEvent
LiveActivityBinding
PushOutbox
PushAttempt
```

`Run` is the read projection. `RunEvent` is received explanatory history.
`PushOutbox` is desired delivery work. `LiveActivityBinding` connects one Run to
one device Activity token.

ADR 0002 changes the conceptual importance of these tables:

```text
Run projection     authoritative Server-side current state
RunEvent feed      best effort, not necessarily complete
```

### Step 8 — Projection logic

Open:

```text
server/app/services.py
```

Read in this order:

1. `run_snapshot()`
2. `ingest_events()`
3. `_validate_transition()`
4. `schedule_run_pushes()`
5. `live_content_state()` / `live_payload()`
6. `create_notification()`
7. `cleanup_retention()`

This is the central Server file.

Current-versus-target differences to notice:

| Current implementation | Accepted target |
|---|---|
| older `seq` raises out-of-order HTTP 409 | older revision is acknowledged as `ignored_stale` |
| the feed assumes accepted event rows | replaceable state may be coalesced or omitted |
| heartbeat interval originates at 15 seconds | default 60 seconds, and other updates count as activity |
| Live Activity `stale-date` is 60 seconds | default stale horizon is 10 minutes |
| state transition validation is relatively strict | execution state stays local-authoritative, Server tolerates missing intermediate revisions |

Terminal immutability should remain, but a self-contained terminal snapshot must
be accepted even when intermediate revisions are absent.

## 6. Fourth reading pass: transactional push delivery

### Step 9 — Outbox worker

Open:

```text
server/app/outbox.py
server/worker/main.py
server/app/apns.py
```

Read the flow:

```text
PushOutbox pending row
→ OutboxProcessor.process_one()
→ decrypt target token
→ choose APNs headers
→ provider.send()
→ PushAttempt record
→ sent / retry / invalidated / failed
```

`server/worker/main.py` drains the outbox independently of API requests, so APNs
latency cannot hold open Run ingest transactions.

`server/app/apns.py` has two implementations:

```text
MockAPNsProvider         deterministic CI path
ProductionAPNsProvider   HTTP/2 + ES256 Apple path
```

When studying failures, separate these two questions:

1. Did Run projection converge in PostgreSQL?
2. Did APNs presentation delivery succeed?

A push failure must not corrupt or roll back the Run projection.

## 7. Fifth reading pass: native iOS client

### Step 10 — App composition

Open:

```text
apps/ios/RunBuoyApp/RunBuoyApp.swift
apps/ios/RunBuoyApp/AppConfiguration.swift
apps/ios/RunBuoyApp/Routing.swift
```

`RunBuoyApp.swift` constructs the read API, Keychain identity store, cache, app
store, notification coordinator, ActivityKit coordinator, and router.

`AppConfiguration` currently reads a fixed API base URL from Info.plist.
`Routing` handles tabs and deep links such as:

```text
runbuoy://runs/<run-id>
```

### Step 11 — Wire models and Read API

Open:

```text
apps/ios/RunBuoyApp/Models.swift
apps/ios/RunBuoyApp/ReadOnlyAPIClient.swift
```

Read `RunSnapshot`, `RunFeedEvent`, `RunDetail`, `MachineSnapshot`, and
`RichMessage` first. Notice the forward-compatible status decoding and multiple
accepted envelope shapes.

In `ReadOnlyAPIClient.swift`, inspect `DeviceAPIEndpoint` and `RunBuoyAPI`. The
absence of execute, cancel, input, approval, and terminal endpoints is an
architectural property, not just a UI choice.

### Step 12 — Store and cache

Open:

```text
apps/ios/RunBuoyApp/RunBuoyStore.swift
apps/ios/RunBuoyApp/CacheStore.swift
apps/ios/RunBuoyApp/SecureStore.swift
```

`RunBuoyStore.refresh()` fetches Runs, Machines, and Messages concurrently,
updates stable row models, and saves a local snapshot. If refresh fails while
cached data exists, it keeps the data and presents an offline/delayed state.

Under ADR 0002, the desired UI language should evolve from a hard offline state
toward neutral freshness:

```text
Updates may be delayed
Status currently unavailable
Last updated …
```

### Step 13 — Screens

Read:

```text
apps/ios/RunBuoyApp/RunsView.swift
apps/ios/RunBuoyApp/RunDetailView.swift
apps/ios/RunBuoyApp/MachinesView.swift
apps/ios/RunBuoyApp/SettingsView.swift
apps/ios/RunBuoyApp/StatusComponents.swift
apps/ios/RunBuoyApp/OnboardingView.swift
apps/ios/RunBuoyApp/PairMachineView.swift
apps/ios/RunBuoyApp/QRScannerView.swift
```

A useful order is:

```text
RunsView → StatusComponents → RunDetailView → MachinesView → Onboarding
```

The UI should only read, copy, share, pair, change local receiving preferences,
or remove a subscription. It must never mutate a Machine process.

Compatibility warning: the current visual revision targets iOS 26 and uses iOS
26 presentation APIs. The accepted requirement is iOS 18 functionality with
iOS 26 enhancements behind availability checks.

### Step 14 — APNs and Live Activity token lifecycle

Open:

```text
apps/ios/RunBuoyApp/NotificationCoordinator.swift
apps/ios/RunBuoyApp/ActivityTokenCoordinator.swift
apps/ios/RunBuoyShared/RunActivityAttributes.swift
apps/ios/RunBuoyWidgets/RunLiveActivityWidget.swift
```

Follow these token flows separately:

```text
ordinary APNs device token
ActivityKit push-to-start token
per-Activity update token
```

`RunActivityAttributes.ContentState` must remain byte-for-byte compatible with
the Server `content-state` payload shape.

The widget is a projection of the newest accepted snapshot. It must tolerate
missing intermediate progress updates and must not show failure just because the
content is old.

## 8. Read the tests as executable specifications

Read these after the implementation files:

```text
packages/protocol/tests/test_protocol.py
cli/tests/test_worker.py
cli/tests/test_networking.py
cli/tests/test_persistence.py
server/tests/test_api.py
server/tests/test_push.py
apps/ios/RunBuoyTests/
scripts/e2e_smoke.sh
scripts/check_read_only_boundary.py
.github/workflows/ci.yml
```

`scripts/e2e_smoke.sh` currently exercises:

```text
real CLI/tmux
→ FastAPI/PostgreSQL
→ mock APNs
→ read projection
```

It uses HTTP calls to simulate the iOS token-registration side; it is not a
physical-iPhone APNs test.

The next test additions implied by ADR 0002 are:

- dropped intermediate progress updates;
- newer revision before older revision;
- stale acknowledgement and queue removal;
- random duplication and reordering;
- hours-long disconnect followed by terminal convergence;
- missing heartbeat without execution transition;
- APNs loss followed by Read API convergence;
- iOS 18 build with iOS 26 availability paths.

## 9. One Run end-to-end call graph

Use this checklist when stepping through a debugger:

```text
runbuoy run
  cli/app.py::run_command
    models.py::RunManifest
    persistence/store.py::create_run
    executors/tmux.py::TmuxExecutor.start

runbuoy _worker
  worker/runtime.py::Worker.run
    Worker._run_target
      subprocess.Popen
      progress adapter
      Worker.emit
        persistence/store.py::append_event
      Worker._upload_loop
        networking/client.py::flush_pending
          RemoteClient.upsert_run
          RemoteClient.upload_events

FastAPI
  server/app/api.py::upsert_run
  server/app/api.py::ingest_run_events
    server/app/services.py::ingest_events
      Run projection update
      schedule_run_pushes
      PushOutbox insert/update

Push worker
  server/app/outbox.py::OutboxProcessor.process_one
    server/app/apns.py::APNsProvider.send

Native iOS
  ReadOnlyAPIClient.listRuns / runDetail
    RunBuoyStore.refresh / detail
      RunsView / RunDetailView

ActivityKit
  ActivityTokenCoordinator
  RunActivityAttributes
  RunLiveActivityWidget
```

## 10. Practical study plan

### 90-minute orientation

1. PRD + ADRs — 15 minutes
2. architecture + protocol — 10 minutes
3. CLI `run_command` + Worker — 20 minutes
4. SQLite + `flush_pending` — 15 minutes
5. Server `ingest_events` + outbox — 20 minutes
6. iOS API/store/widget — 10 minutes

### Half-day deep dive

1. Run `./scripts/e2e_smoke.sh`.
2. Add temporary breakpoints/logging at:
   - `Worker.emit()`;
   - `flush_pending()`;
   - `ingest_events()`;
   - `OutboxProcessor.process_one()`.
3. Run a 10-second determinate example.
4. Inspect the local SQLite event rows.
5. Inspect the Server Run projection and mock push attempts.
6. Decode the same JSON using the iOS model tests.

### Best first code change

A focused first contribution is to implement ADR 0002 stale-update semantics:

1. Server returns `ignored_stale` instead of HTTP 409 for older revisions.
2. Client marks `ignored_stale` rows delivered.
3. Add a test where revision 2 arrives before revision 1.
4. Verify progress remains at revision 2 and revision 1 leaves the retry queue.

This change crosses the CLI/Server contract but is small enough to understand in
one sitting, making it a good entry point into the codebase.
