# RunBuoy Event Protocol

RunBuoy Event Protocol version 1 carries safe execution state from a Machine
to the Server and then to read-only iPhone presentations. The canonical
machine-readable contracts live in [`packages/protocol`](../../packages/protocol).

## Ordering and delivery

Every Run has an integer `seq` beginning at 1. The Machine commits an event
and its sequence to local SQLite before upload. Upload is at least once.
The Server enforces uniqueness on both `event_id` and `(run_id, seq)`.
Duplicates are successful no-ops; older events remain in the append-only feed
but cannot replace a newer snapshot.

Terminal states (`SUCCEEDED`, `FAILED`, `CANCELLED`, `LOST`) are immutable.
Client timestamps describe occurrence time, while the Server separately
records receipt time.

## States

- Execution: `CREATED`, `STARTING`, `RUNNING`, `SUCCEEDED`, `FAILED`,
  `CANCELLED`, `LOST`
- Health: `HEALTHY`, `STALE`, `OFFLINE`
- Attention: `NONE`, `INFORMATION`, `WARNING`, `ACTION_REQUIRED`

## Events

`run.created`, `run.starting`, `run.started`, `run.progress`,
`run.phase_changed`, `run.message`, `run.attention_required`,
`run.heartbeat`, `run.succeeded`, `run.failed`, `run.cancelled`, and
`run.lost` are the only version 1 Run events.

Unknown object fields are ignored. Unknown event types require a newer
protocol version and are rejected with a stable validation error.

`run.created.occurred_at` is the Run creation time. The projection's
`updated_at` is the monotonic occurrence time of the newest accepted Machine
event. Any event proves that the Machine-to-Server path was alive at that
time; a heartbeat supplies that proof every 15 seconds while no other event
does. Live Activities display `updated_at - created_at` as a static,
Machine-confirmed duration rather than advancing an iPhone-local timer.

## Progress

Determinate progress includes non-negative `current`, positive `total`, a
clamped `fraction` in `0...1`, and one of `explicit`, `adapter`, `regex`, or
`lines` as its source. Indeterminate progress never invents a percentage or
ETA. It may include elapsed time, a phase, and the last safe update.

Machine display names have one write authority: the CLI. A paired Machine may
update only its own Server projection, while Devices and iOS remain read-only.
Active Live Activities receive the current name in content state; their
creation attributes retain the initial name only as a compatibility fallback.

## Privacy

Default event payloads contain only a safe title, Machine display name, state,
progress, phase, safe summary, timestamps, exit code, and connection health.
They do not contain argv, cwd, environment, source files, stdout, stderr,
terminal frames, credentials, or user input. The fixture
`default-upload.json` is checked in CI to keep that boundary executable.
