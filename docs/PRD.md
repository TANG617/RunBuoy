# RunBuoy MVP product requirements

## Product

RunBuoy — **Keep every run in sight.**

RunBuoy delivers read-only status for commands, builds, experiments, and AI
agent runs from a Mac or Linux machine to an iPhone. It combines a local
`runbuoy` CLI, an outbound-only synchronization service, a Server projection
and APNs plane, and a native SwiftUI app.

RunBuoy is a status buoy, not an audit log or remote-control system. Its primary
job is to converge the iPhone onto the newest useful state despite packet loss,
reordering, duplicate delivery, long disconnects, delayed APNs delivery, and
temporary heartbeat loss.

## Permanent one-way boundary

Execution data flows only:

```text
Machine → Server → iPhone
```

The iPhone can bootstrap its installation, register rotating notification and
ActivityKit tokens, claim one-time pairing sessions, read projections, update
its own display preferences, and delete receiving subscriptions. It can never
start, cancel, retry, approve, signal, attach, type into, or otherwise mutate a
process or Machine. The Server has no machine inbox, command queue, terminal
endpoint, tunnel, control WebSocket, or polling command channel.

This is a permanent product and security invariant, not an MVP omission.

## Delivery model

RunBuoy uses **latest-state-wins eventual consistency**, not strict event-log
replay.

The protocol distinguishes two delivery classes:

1. **Replaceable state** — progress, phase, safe message, attention, heartbeat,
   and presentation-health hints. These values may be coalesced, skipped, arrive
   out of order, or be permanently omitted. A newer revision supersedes an older
   revision.
2. **Durable milestones** — Run creation metadata, explicit terminal result,
   and one-time rich notifications. These records remain locally durable until
   the Server acknowledges them.

Per-Run `seq` is a monotonically increasing revision, not a requirement that the
Server receive every integer. The Server MUST:

- apply an update when `seq` is newer than the current projection revision;
- accept an exact duplicate as an idempotent no-op;
- acknowledge an older update as `ignored_stale` rather than returning a retryable
  error;
- allow revision gaps;
- prevent an older revision from regressing progress or other projected fields.

A terminal update MUST carry a complete final snapshot sufficient to converge a
Server that missed all intermediate updates. It includes the final execution
status, final progress when known, phase, safe message, exit code, start/end
timestamps, and termination reason when applicable.

The Run Feed is best-effort explanatory history. It is useful for reading major
changes, but it is not guaranteed to contain every intermediate progress or
heartbeat update.

## Execution and health semantics

Execution status is local truth produced by the Worker or a conservative local
reconciler:

```text
CREATED
STARTING
RUNNING
SUCCEEDED
FAILED
CANCELLED
LOST
```

`SUCCEEDED`, `FAILED`, `CANCELLED`, and `LOST` are terminal. The Server and
iPhone MUST NOT infer an execution transition from missing network traffic.
Specifically, missing heartbeats, APNs delay, Machine sleep, Server restart, or
network loss MUST NOT convert `RUNNING` into `FAILED` or `LOST`.

`LOST` may only be emitted after the local Machine determines that the Worker,
target process group, tmux session, and final result are unavailable under the
local reconciliation policy.

Connection health is a soft presentation hint derived from Server receipt time,
not a second execution state machine. Default presentation thresholds are:

- less than 5 minutes since the newest receipt: no delay warning;
- 5–30 minutes: **Updates may be delayed**;
- more than 30 minutes: **Status currently unavailable**.

The UI should retain the newest known progress and show its last-update time.
Network uncertainty uses neutral language and styling; it is not shown as task
failure.

## Network-tolerance requirements

- The target process never depends on Server or APNs availability.
- Every locally generated durable milestone is written to SQLite before upload.
- Replaceable state may be coalesced by `(run_id, state_kind)` while pending.
- Terminal snapshots remain pending indefinitely until acknowledged or the user
  explicitly deletes local state.
- Retries use bounded exponential backoff with jitter.
- A stale acknowledged update is removed from the local queue and is not retried
  forever.
- Network recovery sends the newest useful snapshot rather than replaying every
  historical progress or heartbeat sample.
- APNs is a hint channel. App foreground refresh through the Read API is the
  convergence path when pushes are dropped.
- The iOS client keeps cached state during outages and labels it with the last
  successful refresh time.

Heartbeat is a soft liveness sample. The default heartbeat interval is 60
seconds, and any progress, phase, message, attention, or terminal update also
counts as activity. Pending heartbeats are coalesced; historical heartbeats are
never replayed in bulk and never directly trigger APNs.

## MVP users and jobs

- A developer wants to leave a long build running and see honest progress.
- A researcher wants to follow an experiment without uploading its data or full
  logs.
- An AI-assisted developer wants an attention notification without granting a
  phone remote-control or approval authority.
- A self-hoster wants deterministic mock APNs tests and documented production
  APNs configuration.

## Functional requirements

### Local execution

`runbuoy run -- <command>` creates a Run, derives a safe title, persists a local
manifest and synchronization queue, launches a tmux-owned Worker, runs the
command in a PTY/process group, mirrors output locally, records the real exit
code, and uploads only safe state. Network failure never stops the command.

`list`, `status`, `logs`, `attach`, and `cancel` are local-only. Local cancel
escalates SIGINT, SIGTERM, then SIGKILL against the process group.

### Progress

Structured socket updates, matched lines, regular expressions, and honest
indeterminate progress are supported. RunBuoy never derives a percentage or ETA
from elapsed time. Structured socket messages require a per-Run ephemeral token.

Progress may jump forward after a disconnect. It must never move backward merely
because an older network update arrives late.

### Pairing

An anonymous device installation can pair multiple Machines using a five-minute,
single-use QR challenge. The QR contains no long-lived credential. Exchange
secrets are stored only as hashes. Credentials are scoped by actor.

### Server and push

The Server validates versioned revisions; enforces ownership, scope, idempotency,
stale-update suppression, and terminal immutability; updates a Run projection;
and writes desired push state transactionally. An independent worker coalesces
and sends mock or production APNs requests.

Live Activities start only for Runs still active after five seconds and are
limited to two per device. Ordinary progress updates are coalesced. Short
successes remain history-only; short failures use a normal notification.

The default Live Activity stale horizon is 10 minutes. Staleness retains the
newest known progress and adds a neutral last-update indication. Only an explicit
terminal snapshot ends the Live Activity as success, failure, cancellation, or
loss.

### Native iOS

The compatibility baseline is **iOS 18**. iOS 18 must provide all functional
capabilities. iOS 26 may use Liquid Glass and newer presentation APIs as optional
visual enhancements behind availability checks with iOS 18 fallbacks.

The native app provides Runs and Settings tabs, active/recent/message sections,
offline cache states, read-only Run detail and feed, Machines, pairing,
notification preferences, deep links, and Live Activities. The widget has no
buttons. Accessibility, Dynamic Type, reduced motion, contrast, and
English/Simplified Chinese are first-class requirements.

The repository currently contains an iOS 26-targeted visual revision. That is an
implementation gap against this accepted compatibility requirement and must be
resolved by restoring an iOS 18 deployment target and availability-gating iOS 26
presentation APIs.

### Webhooks

Scoped, revocable bearer credentials accept rich notifications and external Run
state. Secrets never appear in URLs. Safe rich text supports only a
non-executable Markdown subset and HTTPS links.

## Privacy defaults

Remote payloads exclude full argv, cwd, environment, source and file content,
stdout/stderr, terminal frames, user input, API keys, SSH keys, and cloud
credentials. Full logs remain local. `--share-log-tail 1..100` is explicit,
bounded, stripped of ANSI, redacted, labeled in iOS, and retained by the Server
for at most 24 hours.

## Non-goals

- Remote terminal, SSH, tunnel, or tmux phone client
- Server-initiated Machine work
- Remote cancel/retry/signal/stdin
- Agent approvals, replies, or questions
- Complete, gap-free replay of progress or heartbeat history
- Treating network silence as execution failure
- Email accounts, teams, billing, or Windows in the MVP
- Redis, microservices, WebSocket, or continuous log streaming
- Fabricated progress or ETA

## Acceptance

The normative scenarios are executable in protocol, CLI, Server, APNs mock, and
boundary tests:

- long and short Runs;
- structured, lines, regex, and indeterminate progress;
- offline recovery after minutes or hours;
- random loss of replaceable updates;
- duplicate and out-of-order delivery;
- a newer revision arriving before an older revision;
- stale updates acknowledged and removed instead of retried forever;
- progress never regressing;
- explicit terminal convergence even when intermediate updates are absent;
- local cancel and locally confirmed `LOST`;
- APNs loss followed by Read API convergence;
- token rotation, webhook, concurrency limits, and privacy;
- iOS 18 functional compatibility with optional iOS 26 visual enhancement;
- absence of remote-control API and UI.

Passing acceptance does not require every intermediate event to survive. It
requires the newest projection and explicit terminal result to converge without
false failure under substantial network volatility.
