# Security boundary

RunBuoy follows a least-privilege principle: the phone can observe a run but cannot control it.

## One-way architecture

```text
Machine → RunBuoy Server → iPhone
```

The iPhone can pair, receive notifications, read run status, and remove its own receiving subscription. It cannot:

- Start, cancel, or retry a task on the computer
- Send signals, keyboard input, or terminal data
- Approve, reply to, or control an agent
- Establish SSH, tunnels, terminal streams, or control WebSockets

## Credentials

- Machines and devices use separate, scoped random bearer credentials.
- The server stores only strong hashes of long-lived credentials.
- Local credentials use Keychain or Secret Service when available.
- APNs and Live Activity tokens are encrypted on the server.
- A pairing challenge expires after five minutes and cannot be replayed.

## Local process isolation

The RunBuoy Worker starts the original command from a protected manifest instead of concatenating it into a shell string. Cancellation exists only on the local computer and targets the recorded process group.

The complete security design, threat model, and automated boundary tests are available in the [GitHub repository](https://github.com/TANG617/RunBuoy/tree/main/docs).

To report a security issue, follow the repository’s [security policy](https://github.com/TANG617/RunBuoy/security/policy) and use [GitHub private vulnerability reporting](https://github.com/TANG617/RunBuoy/security/advisories/new). Do not include vulnerability details in a public issue. For non-security help, use [Support](/en/support).
