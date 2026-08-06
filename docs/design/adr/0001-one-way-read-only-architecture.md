# ADR 0001: One-way, read-only mobile architecture

- Status: Accepted
- Date: 2026-07-26
- Baseline: `8a8b521dd26381149d3b89d5dd19ddd5b4d18d81`

## Context

The repository is an exact fork of `sethwebster/rzr` at the baseline above.
Its terminal streaming, public tunnel, remote keyboard, WebSocket, Expo,
React Native, WebView, SwiftTerm, and server-to-machine interaction are
incompatible with RunBuoy's product boundary.

## Decision

RunBuoy has four explicit planes:

1. The local execution plane runs commands and stores full local logs.
2. The synchronization plane uploads safe, versioned events over outbound
   HTTPS with at-least-once delivery.
3. The server projection and push plane validates events, projects read
   models, and sends APNs payloads through a transactional outbox.
4. The native iOS presentation plane reads projections and displays
   notifications and Live Activities.

Execution data only flows `Machine → Server → iPhone`. Device writes are
limited to bootstrap, token lifecycle, pairing claims, local preferences, and
subscription deletion. There is no machine inbox, remote command queue,
WebSocket, terminal stream, input API, execute API, or signal API.

Local `attach`, `logs`, and `cancel` operate only against local tmux, files,
SQLite, process groups, and Unix domain sockets. No server response can become
a command or signal.

## Protocol invariants

- Protocol version 1 uses JSON, UTC ISO-8601 timestamps, ordered UUIDs, and
  per-Run monotonically increasing integer `seq`.
- `(run_id, seq)` and `event_id` are unique.
- Duplicate events are accepted idempotently.
- A stale sequence cannot overwrite a newer projection.
- Terminal execution states are immutable.
- Unknown fields are ignored for forward compatibility.
- Full argv, cwd, environment, source, stdout, stderr, tokens, and secrets are
  absent from default remote payloads.

## Upstream disposition

The new implementation is clean-room Python and Swift. The original MIT
license is retained. The old Expo app, SwiftTerm vendoring, terminal server,
Cloudflare worker, tunnels, billing, and remote-control code will be removed.
If a small upstream implementation is later reused, its file-level origin and
modification will be recorded in `docs/code-provenance.md`.

## Consequences

RunBuoy deliberately cannot be used to operate a computer from iPhone. A
network outage may delay status delivery but cannot interrupt the target
process. Real APNs delivery requires external Apple credentials and a physical
device; mock APNs remains the deterministic CI path.
