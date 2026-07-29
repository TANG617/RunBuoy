# RunBuoy MVP product requirements

## Product

RunBuoy — **Keep every run in sight.**

RunBuoy delivers read-only status for commands, builds, experiments, and AI
agent runs from a Mac or Linux machine to an iPhone. It combines a local
`runbuoy` CLI, an outbound-only event synchronization service, a projection
and APNs server, and a native SwiftUI app.

## Permanent boundary

Execution data flows only:

```text
Machine → Server → iPhone
```

The iPhone can bootstrap its installation, register rotating notification and
ActivityKit tokens, claim one-time pairing sessions, read projections, update
its own display preferences, and delete receiving subscriptions. It can never
start, cancel, retry, approve, signal, attach, type into, or otherwise mutate
a process or Machine. The Server has no machine inbox, command queue,
terminal endpoint, tunnel, control WebSocket, or polling command channel.

This is a permanent product and security invariant, not an MVP omission.

## MVP users and jobs

- A developer wants to leave a long build running and see honest progress.
- A researcher wants to follow an experiment without uploading its data or
  full logs.
- An AI-assisted developer wants an attention notification without granting a
  phone remote-control or approval authority.
- A self-hoster wants deterministic mock APNs tests and documented production
  APNs configuration.

## Functional requirements

### Local execution

`runbuoy run -- <command>` creates a Run, derives a safe title, persists a
local manifest and event queue, launches a tmux-owned Worker, runs the command
in a PTY/process group, mirrors output locally, records the real exit code,
and uploads only safe events. Network failure never stops the command.

`list`, `status`, `logs`, `attach`, and `cancel` are local-only. Local cancel
escalates SIGINT, SIGTERM, then SIGKILL against the process group.

### Progress

Structured socket events, matched lines, regular expressions, and honest
indeterminate progress are supported. RunBuoy never derives a percentage or
ETA from elapsed time. Structured socket messages require a per-Run ephemeral
token.

### Pairing

An anonymous device installation can pair multiple Machines using a five
minute, single-use QR challenge. The QR contains no long-lived credential.
Exchange secrets are stored only as hashes. Credentials are scoped by actor.

### Server and push

The Server validates versioned, ordered events; enforces ownership, scope,
idempotency, legal state transitions, and terminal immutability; updates a Run
projection; and writes desired push state transactionally. An independent
worker coalesces and sends mock or production APNs requests.

Live Activities start only for Runs still active after five seconds, are
limited to two per device, update no faster than every three seconds for
ordinary progress, and advance their displayed elapsed time only from
Machine-confirmed events. Fifteen-second heartbeats keep the duration fresh;
after 60 seconds without confirmation the presentation becomes stale without
claiming that execution stopped. Ended activities use ActivityKit's default
dismissal behavior. Short successes remain history-only; short failures use a
normal notification.

### Native iOS

The native iOS 18 app provides Runs and Settings tabs, active/recent/message
sections, offline cache states, read-only Run detail and feed, Machines,
pairing, notification preferences, deep links, and Live Activities. The
widget has no buttons. Accessibility, Dynamic Type, reduced motion, contrast,
and English/Simplified Chinese are first-class requirements.

### Webhooks

Scoped, revocable bearer credentials accept rich notifications and external
Run events. Secrets never appear in URLs. Safe rich text supports only a
non-executable Markdown subset and HTTPS links.

## Privacy defaults

Remote payloads exclude full argv, cwd, environment, source and file content,
stdout/stderr, terminal frames, user input, API keys, SSH keys, and cloud
credentials. Full logs remain local. `--share-log-tail 1..100` is explicit,
bounded, stripped of ANSI, redacted, labeled in iOS, and retained by the
Server for at most 24 hours.

## Non-goals

- Remote terminal, SSH, tunnel, or tmux phone client
- Server-initiated Machine work
- Remote cancel/retry/signal/stdin
- Agent approvals, replies, or questions
- Email accounts, teams, billing, or Windows in the MVP
- Redis, microservices, WebSocket, or continuous log streaming
- Fabricated progress or ETA

## Acceptance

The normative scenarios are executable in protocol, CLI, Server, APNs mock,
and boundary tests: long/short Runs, all progress modes, offline recovery,
duplicates/out-of-order delivery, local cancel, token rotation, webhook,
concurrency limits, privacy, and absence of control APIs/UI.
