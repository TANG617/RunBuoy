# Architecture

## Planes

```mermaid
flowchart LR
  subgraph M["Local Execution Plane — trusted Machine"]
    C["runbuoy CLI"] --> DB[("SQLite event queue")]
    C --> T["tmux"]
    T --> W["Worker + PTY/process group"]
    W --> L["local logs/result"]
    W --> DB
    S["Unix socket: emit/local cancel"] --> W
  end
  subgraph Y["Synchronization Plane"]
    DB -->|"outbound HTTPS; safe events only"| API["FastAPI ingest"]
  end
  subgraph P["Server Projection / Push Plane"]
    API --> PG[("PostgreSQL")]
    PG --> O["transactional outbox"]
    O --> AP["APNs worker"]
  end
  subgraph I["Native iOS Presentation Plane"]
    AP --> LA["Notification / Live Activity"]
    R["Read API"] --> APP["SwiftUI app + local cache"]
  end
  PG --> R
```

There is deliberately no arrow from iPhone or Server to the local execution
plane.

## Run sequence

```mermaid
sequenceDiagram
  participant U as User
  participant C as CLI
  participant W as Local Worker
  participant A as API
  participant D as PostgreSQL
  participant P as Push Worker/APNs
  participant I as iPhone
  U->>C: runbuoy run -- command
  C->>C: safe manifest + SQLite + tmux
  C->>W: _worker --manifest path
  W->>W: PTY + independent process group
  W->>D: queue created/started/progress locally
  W->>A: outbound HTTPS event batch
  A->>D: event + projection + outbox (one transaction)
  P->>D: lease desired push
  P->>I: APNs start/update/end or alert
  I->>A: GET read projections
  A-->>I: read-only Run/feed data
```

## Sources of truth

- The target process and final result file are the execution truth.
- Local SQLite is the durable upload and sequence truth.
- tmux provides local persistence and attach only; pane capture is not a
  lifecycle source.
- PostgreSQL stores append-only received events and a derived read projection.
- APNs and iOS caches are presentations, never execution controllers.

## Failure recovery

Events are committed locally before upload. Batches are retried with bounded
backoff; duplicates are accepted idempotently. A stale sequence cannot
regress a projection. Terminal events are uploaded immediately and remain in
the local outbox until acknowledged. After the target exits, the Worker remains
alive for a bounded terminal-delivery window and continues respecting the
outbox backoff schedule. `runbuoy doctor --repair` is the explicit recovery
path for delivery still queued after that window; it retries without changing
local execution state or deleting failed records. Server push work is
transactional with projection changes and retried independently; APNs 410
invalidates the target token rather than retrying forever.

If APNs is unavailable, Runs remain readable. If the Server is unavailable,
the local process continues and events drain after recovery. If a heartbeat
expires, presentation health becomes stale/offline without inventing an
execution transition.

## Trust boundaries

- Local manifests and logs may contain sensitive execution data and use
  restrictive filesystem permissions.
- The Unix socket is local, mode-restricted, and authenticated with an
  ephemeral Run token.
- Machine and Device bearer credentials have non-overlapping scopes.
- Exchange secrets and API credentials are strongly hashed.
- APNs device and activity tokens are encrypted at rest.
- QR payloads are short-lived challenges and never long-lived credentials.
- iOS renders structured data and a safe Markdown subset without WebView.
