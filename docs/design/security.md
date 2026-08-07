# Security and privacy

RunBuoy minimizes authority: a phone can observe execution but cannot control
it. The definitive architectural decision is
[ADR 0001](adr/0001-one-way-read-only-architecture.md).

## Credentials

Machine and Device credentials are random bearer values with distinct scopes.
Only strong hashes are stored by the Server. Local credentials use Keychain
or Secret Service when available; a fallback file is mode `0600`. Secrets
must never appear in config output, logs, exceptions, URLs, QR codes, or
structured log fields.

APNs device, push-to-start, and per-activity update tokens are encrypted using
the configured server-side encryption key. Token rotation replaces the
effective target. An APNs `410 Unregistered` response invalidates the token.

## Pairing

Pairing sessions expire after five minutes and are single use. The CLI gets a
one-time exchange secret; the Server keeps only its hash. The iPhone claims a
challenge using its Device credential. Exchange fails after claim has already
been consumed, expiry, workspace mismatch, or replay.

## Local process isolation

The CLI passes a protected manifest path to tmux rather than interpolating the
user command into a shell string. The Worker creates the PTY and process
group. Only the local Worker may interpret local cancel, and it targets the
recorded process group with bounded escalation. No Server response is parsed
as a command or signal.

## Data minimization

Default uploads contain only a safe title and structured status. Full command,
argv, cwd, environment, file content, source, stdout/stderr, terminal frames,
and input remain local. Log-tail sharing is explicit, bounded, ANSI-stripped,
redacted, labeled, and expires after 24 hours.

## Automation

`scripts/check_read_only_boundary.py` rejects forbidden OpenAPI/server routes,
WebSocket routes, Machine command polling, terminal/mobile runtime
dependencies, mutation labels in iOS, and sensitive default fixture keys.
Runtime authorization tests verify that Device credentials receive 403 on
Machine write APIs and Machine credentials cannot retrieve Device secrets.

## Revocation and deletion

Stopping reception deletes only the authenticated Device subscription. Machine
revocation invalidates Machine and Hook bearers without sending a command to the
Machine. Device reset invalidates the authenticated Device bearer and all of its
push targets. Full anonymous Workspace deletion requires a short-lived,
Device-bound challenge and removes credentials and user data in one transaction.
Lifecycle endpoints return stable JSON error codes and deliberately use request
bodies—not URLs—for deletion challenges and bearer material.

Online deletion cannot rewrite already-created encrypted backup archives. Those
copies remain inaccessible to product APIs and expire according to the operator's
documented backup retention period.

Report vulnerabilities privately as described in the repository `SECURITY.md`.
