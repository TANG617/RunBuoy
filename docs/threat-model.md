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
| Pairing short-code guessing | Authenticated lookup, five-minute expiry, per-Device rate limit, generic invalid/expired response |
| Event replay or reordering | Unique event/sequence constraints and monotonic projection |
| Terminal state regression | Terminal projection is immutable |
| Process output leaks secrets | Output stays local; opt-in tail is bounded and redacted |
| Token leaks through logs | Structured redaction and no token interpolation |
| APNs token at-rest disclosure | Application-layer encryption with rotation |
| Push amplification | Coalescing, minimum update interval, per-device activity cap |
| Webhook URL leakage | Bearer secret in Authorization header, not URL |
| Malicious Markdown | No HTML/WebView; allowlisted formatting and HTTPS links |
| Local socket spoofing | Per-Run path permissions and ephemeral token |
| Server outage kills a Run | Upload failure is isolated from execution |

## Residual risks

Safe titles and explicit safe messages can still reveal project context, so
users must choose them deliberately. Same-user local malware can read files
and process memory allowed by the OS account. Push delivery is best effort,
and an unavailable Server or APNs can make status stale. Server operators can
read structured metadata unless a future end-to-end encryption design is
added. These risks do not grant remote execution authority.
