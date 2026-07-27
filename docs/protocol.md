# RunBuoy Event Protocol

RunBuoy Event Protocol version 1 carries safe execution state from a Machine to
the Server and then to read-only iPhone presentations. The canonical
machine-readable contracts live in [`packages/protocol`](../packages/protocol).

The protocol is optimized for high network volatility and newest-state
convergence. It is not a complete telemetry or audit-log protocol.

## Revisions, ordering, and delivery

Every Run has a monotonically increasing integer `seq` beginning at 1. `seq` is
a state revision, not a requirement that the Server receive every integer.

The Machine commits locally before upload. Upload is at least once. The Server
enforces uniqueness on both `event_id` and `(run_id, seq)`, but revision gaps are
legal.

Server behavior:

- `seq > current_revision`: apply the update and advance the projection;
- exact duplicate `event_id + run_id + seq + type`: successful no-op;
- `seq <= current_revision`: successful stale no-op, reported as
  `ignored_stale`;
- a stale update cannot replace or regress a newer snapshot;
- a missing intermediate revision does not block later revisions.

A representative response is:

```json
{
  "applied": ["event-7"],
  "duplicates": ["event-7-retry"],
  "ignored_stale": ["event-2-late"],
  "last_seq": 7,
  "snapshot": {}
}
```

The client treats all three acknowledged categories as delivered. It must not
retry an `ignored_stale` update forever.

Client timestamps describe occurrence time. The Server separately records
receipt time and uses receipt time for freshness, scheduling, and timeout
presentation.

## Delivery classes

### Replaceable state

The following values describe the newest known state and may be coalesced,
skipped, reordered, or permanently omitted:

- progress;
- phase;
- safe message;
- attention status;
- heartbeat;
- presentation-health hints.

While offline, the local queue should retain only the newest pending value per
`(run_id, state_kind)` where practical. Historical heartbeat and fine-grained
progress samples are not replayed in bulk after recovery.

### Durable milestones

The following remain locally durable until acknowledged:

- initial Run metadata;
- explicit terminal result;
- one-time rich Notification.

A terminal update is a self-contained final snapshot. It carries the final
execution status, final progress when known, phase, safe message, exit code,
start/end timestamps, and termination reason when applicable. The Server can
therefore converge directly from `CREATED` or an earlier `RUNNING` revision to a
terminal result even when intermediate state never arrived.

## States

Execution states:

- `CREATED`
- `STARTING`
- `RUNNING`
- `SUCCEEDED`
- `FAILED`
- `CANCELLED`
- `LOST`

Terminal states (`SUCCEEDED`, `FAILED`, `CANCELLED`, `LOST`) are immutable once
an explicit terminal snapshot has been accepted.

Only the local Worker or local reconciler may emit execution transitions. The
Server must not infer failure or loss from network silence.

Attention states:

- `NONE`
- `INFORMATION`
- `WARNING`
- `ACTION_REQUIRED`

Health is a presentation freshness hint rather than a strict execution state
machine. A missing heartbeat cannot change execution status.

## Events

Version 1 event names remain:

`run.created`, `run.starting`, `run.started`, `run.progress`,
`run.phase_changed`, `run.message`, `run.attention_required`,
`run.heartbeat`, `run.succeeded`, `run.failed`, `run.cancelled`, and
`run.lost`.

These names do not imply a complete append-only feed. The Server may preserve
major accepted events for explanation while coalescing or omitting replaceable
state from the user-visible feed.

Unknown object fields are ignored. Unknown event types require a newer protocol
version and are rejected with a stable validation error.

## Progress

Determinate progress includes non-negative `current`, positive `total`, a
clamped `fraction` in `0...1`, and one of `explicit`, `adapter`, `regex`, or
`lines` as its source. Indeterminate progress never invents a percentage or ETA.
It may include elapsed time, a phase, and the last safe update.

A newer progress revision may jump forward. A late older revision is ignored,
so network reordering cannot make the progress bar move backward.

## Heartbeat and freshness

Heartbeat is a soft liveness sample. The default emission interval is 60 seconds,
and any progress, phase, message, attention, or terminal update also counts as
activity.

Pending heartbeat updates are coalesced. Heartbeats do not directly trigger
APNs. Missing heartbeat samples only make the presentation older; they do not
produce `FAILED` or `LOST`.

Default UI freshness guidance:

- less than 5 minutes since Server receipt: no warning;
- 5–30 minutes: `Updates may be delayed`;
- more than 30 minutes: `Status currently unavailable`.

The last known state remains visible.

## Live Activity projection

The Live Activity projection is derived from the newest accepted Run snapshot,
not from replaying all events.

The default stale horizon is 10 minutes. Staleness retains the last progress and
shows a neutral age indicator. Only an explicit terminal snapshot causes a
terminal Live Activity end payload.

APNs delivery is best effort. The iOS Read API is the eventual convergence path
when start, update, or end pushes are delayed or dropped.

## Privacy

Default remote state contains only a safe title, Machine display name, execution
state, progress, phase, safe summary, timestamps, exit code, and presentation
freshness.

It does not contain argv, cwd, environment, source files, stdout, stderr,
terminal frames, credentials, or user input. The fixture
`default-upload.json` is checked in CI to keep that boundary executable.
