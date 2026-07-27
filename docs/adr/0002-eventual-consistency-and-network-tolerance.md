# ADR 0002: Latest-state convergence and network tolerance

- Status: Accepted
- Date: 2026-07-27
- Baseline: `29230b551b7999ae51f089bce006cd2ec5953357`

## Context

RunBuoy presents current task status on iPhone over networks that may lose,
duplicate, delay, or reorder updates. It is not an audit-log product. Requiring a
strictly gap-free event stream would keep obsolete progress and heartbeat
records in the retry queue, increase database and network load, and make normal
network disorder appear as a correctness failure.

The product also needs to avoid false execution conclusions. A sleeping laptop,
missing heartbeat, delayed APNs push, or temporary Server outage does not prove
that a target process failed or disappeared.

The current repository implementation still contains stricter event-ordering,
short freshness windows, a 15-second heartbeat, and an iOS 26 deployment target.
Those are implementation details to migrate, not accepted product constraints.

## Decision

### Latest-state-wins

Per-Run `seq` is a monotonic state revision. The Server may accept revision gaps.
A newer revision replaces the current projection, an exact duplicate is an
idempotent no-op, and an older revision is acknowledged as `ignored_stale`.
Older state must not remain in a permanent retry loop.

### Delivery classes

Replaceable state includes progress, phase, safe message, attention, heartbeat,
and presentation-health hints. These records may be coalesced or omitted.

Durable milestones include initial Run metadata, explicit terminal snapshots,
and one-time rich notifications. They remain locally durable until acknowledged.
A terminal snapshot is self-contained and can converge the Server even if every
intermediate state update was lost.

### Weak execution state machine

Execution transitions are produced only by the local Worker or a conservative
local reconciler. The Server does not infer `FAILED` or `LOST` from missing
heartbeats or other network silence.

`LOST` requires local evidence that the Worker, target process group, tmux
session, and final result are unavailable under the local reconciliation policy.

### Soft freshness

Health is presentation freshness derived from Server receipt time. Defaults are:

- under 5 minutes: no warning;
- 5–30 minutes: `Updates may be delayed`;
- over 30 minutes: `Status currently unavailable`.

The UI retains the newest known state and uses neutral language.

Heartbeat defaults to 60 seconds, is coalesced while pending, and does not
trigger APNs. Other state updates count as activity.

### APNs and Live Activity

APNs is best effort. The Read API is the convergence path after dropped pushes.
The default Live Activity stale horizon is 10 minutes. Staleness does not imply
failure and only an explicit terminal snapshot ends the Activity with a terminal
result.

### iOS compatibility

The functional baseline remains iOS 18. iOS 26 presentation APIs are optional
enhancements behind availability checks and must have complete iOS 18 fallbacks.

## Consequences

- The Run Feed is explanatory and best effort, not complete telemetry.
- Progress can jump forward after reconnect, but never backward from a late
  older update.
- Offline recovery sends the newest useful state instead of replaying all
  intermediate progress and heartbeat samples.
- Terminal state has stronger durability than intermediate state.
- Tests must inject packet loss, duplicates, reordering, long disconnects, APNs
  loss, and stale updates.
- Current strict out-of-order errors, 15-second heartbeat, 60-second Activity
  stale horizon, and iOS 26-only deployment are migration targets.

## Required implementation follow-up

1. Return successful `ignored_stale` acknowledgements for older revisions.
2. Permit revision gaps and prevent progress regression.
3. Coalesce pending replaceable state by Run and state kind.
4. Make terminal updates complete snapshots and retain them until acknowledged.
5. Increase heartbeat to 60 seconds and use receipt time for freshness.
6. Increase the default Live Activity stale horizon to 10 minutes.
7. Restore the iOS deployment target to 18 and availability-gate iOS 26 UI.
8. Add network-fault and eventual-convergence test scenarios.
