# Threat model

## Assets

- Machine and Device bearer credentials
- Pairing exchange secrets and challenges
- APNs provider key and device/activity tokens
- Run metadata, safe messages, and optional safe log tails
- Local manifests, full logs, process IDs, sockets, and final result files
- PostgreSQL encryption and backup keys

## Attackers

We consider an Internet attacker, a malicious QR scanner, a user of one
workspace attempting cross-workspace access, an attacker with a leaked
short-lived pairing payload, a webhook spammer, and an untrusted local process
running as a different OS user. A process already running as the same local
user is partly inside the Machine trust boundary; restrictive permissions and
ephemeral socket authentication still reduce accidental and opportunistic
access.

## Abuse cases and mitigations

| Abuse case | Mitigation |
| --- | --- |
| Phone coerces Machine execution | No protocol, endpoint, queue, socket bridge, or Machine poll exists |
| Device token writes Run events | Scope authorization rejects it with 403 |
| Machine reads APNs tokens | No response schema or endpoint returns token plaintext |
| QR replay | Five-minute expiry, single claim/exchange, hashed secret |
| Event replay or reordering | Unique event/sequence constraints and monotonic projection |
| Terminal state regression | Terminal projection is immutable |
| Process output leaks secrets | Output stays local; opt-in tail is bounded and redacted |
| Token leaks through logs | Structured redaction and no token interpolation |
| APNs token at-rest disclosure | Application-layer encryption with rotation |
| Push amplification | Coalescing, minimum update interval, per-device activity cap |
| Webhook URL leakage | Bearer secret in Authorization header, not URL |
| Malicious rich text | No HTML/WebView; current iOS renders plain text and structured fields. Server-valid HTTPS `safe_link` is not consumed by the current iOS model |
| Local socket spoofing | Per-Run path permissions and ephemeral token |
| Server outage kills a Run | Upload failure is isolated from execution |
| Anonymous bootstrap or pairing flood | PostgreSQL-backed HMAC-keyed IP limits, bounded pending pairings, request-body limits, and cleanup |
| Stolen Device or Machine credential | Narrow scopes, workspace ownership checks, Device reset, Machine revoke/revoke-self, and credential revocation timestamps |
| Destructive request by the wrong tenant | Owner-scoped endpoints, rotating short-lived deletion challenge, Device-owner confirmation, and transactional deletion |
| Backup disclosure or tampering | Restricted files, versioned manifest and checksum validation, optional encrypted restic copy, and documented retention |
| Forged forwarding headers bypass limits | `X-Forwarded-For` is accepted only from configured trusted proxy CIDRs and parsed right-to-left |
| Sync cursor tampering or cross-filter reuse | Opaque versioned cursors bind kind and Machine filter; future workspace revisions and malformed cursors are rejected |
| Stale APNs or Live Activity token | Token generations are monotonic; invalid provider tokens invalidate bindings and are not retried indefinitely |
| Cross-workspace object access | Every credential principal and object lookup is workspace-scoped; negative ownership tests cover destructive paths |
| High-cardinality metrics exhaust or leak data | Metrics use fixed route/status/outcome classes and never label workspace, Device, Machine, credential, title, or message |
| Operational logs disclose request content | JSON request logs use an allowlist of request ID hash, route template, method, status, latency, and bounded error class |
| Rate-limit storage failure | Default fail-closed behavior returns 503; explicit fail-open mode is an operator decision and is covered by tests |

## Residual risks

Safe titles and explicit safe messages can still reveal project context, so
users must choose them deliberately. Same-user local malware can read files
and process memory allowed by the OS account. Push delivery is best effort,
and an unavailable Server or APNs can make status stale. Server operators can
read structured metadata unless a future end-to-end encryption design is
added. These risks do not grant remote execution authority.

Online workspace deletion cannot retroactively erase already-created encrypted
backup copies. Operators must expire those copies under the documented backup
retention policy and protect restore access as a separate administrative trust
boundary.
