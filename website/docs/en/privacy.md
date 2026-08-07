---
title: Privacy
description: What RunBuoy synchronizes, what stays local, retention, deletion, and self-hosted responsibilities.
---

# Privacy

RunBuoy is designed around “do not upload by default.” It synchronizes only the limited data needed to show a run’s state on an iPhone. RunBuoy does not sell personal data and does not use synchronized run data for advertising or cross-service tracking.

## Data synchronized by default

- A machine identifier, display name, platform, architecture, and CLI version
- A user-selected safe title and source label
- Run status, health, attention state, phase, structured progress, safe message, timestamps, and exit code
- Notification content that the machine explicitly asks the service to deliver
- Device and app versions, notification preferences, and APNs or Live Activity tokens required for delivery
- Minimal security and delivery metadata, such as credential identifiers, pairing records, delivery attempts, and audit events

## Data kept on the computer by default

- Complete commands and arguments
- Working directory and environment variables
- Source code, file contents, prompts, and user input
- stdout, stderr, terminal frames, and full logs
- API keys, SSH keys, cloud credentials, and local RunBuoy bearer credentials

RunBuoy’s phone path is read-only: the server and iPhone do not receive a capability to start, cancel, retry, or send input to a machine process.

## Optional log snippet

Only an explicit `--share-log-tail 1..100` option uploads a bounded trailing log snippet. Before upload, RunBuoy removes ANSI control sequences, limits size, and redacts common credential patterns. iOS labels the snippet clearly. The Global service retains it for at most 24 hours.

Redaction is defense in depth, not a guarantee that arbitrary secrets can be recognized. Review the content before opting in.

## Default Global retention

Retention windows are maximum defaults for terminal or inactive records, not a promise that every record remains for the entire period.

| Data | Default maximum |
| --- | ---: |
| Optional safe log snippets | 24 hours |
| Pairing challenges and related one-time state | 24 hours |
| Event stream records | 24 hours |
| Terminal runs | 30 days |
| Notification records | 30 days |
| Push delivery attempts and terminal delivery outbox entries | 7 days |
| Security audit events | 90 days |

Active runs and active Live Activities are excluded from age-based cleanup until they become terminal. Cleanup is batched and may occur after a window has elapsed. Deleted data can remain in protected backups until those backups rotate; it is not restored into the live service except for disaster recovery.

## Credentials, delivery tokens, and deletion

Long-lived credentials never belong in URLs, QR codes, or ordinary logs. The service stores hashes of machine and device credentials and encrypts APNs and Live Activity tokens at rest.

- **Stop receiving:** removes that device’s subscription for a machine; it does not stop or control work on the machine.
- **Reset this device:** revokes the device credential and removes its subscriptions, push bindings, and pending delivery state before local app data is cleared.
- **Unpair a machine:** asks the service to revoke that machine credential before deleting the CLI’s local credential. If the server cannot confirm revocation, the normal command preserves the local credential so the user can retry; an explicit local-only operation affects only that computer.
- **Delete a workspace:** requires a short-lived, single-use confirmation challenge and removes workspace-owned machines, devices, runs, events, subscriptions, notification state, delivery state, and audit records in one server transaction.

Deletion cannot cancel or alter a process already running on a machine. Uninstalling the app alone does not prove server-side deletion. Use the in-product reset or deletion action first, or ask for help through [Support](/en/support).

## Website and self-hosting

This static website does not load advertising or third-party analytics by default. GitHub Pages may record access and security logs under its own service policy.

Self-hosted operators choose their server location and can change retention and logging policies. They are responsible for PostgreSQL, encryption keys, APNs credentials, backups, monitoring, deletion requests, and telling their users about any policy that differs from the Global defaults above.

## Contact and updates

The authoritative implementation and change history are in the [GitHub repository](https://github.com/TANG617/RunBuoy). Privacy questions can be filed through [GitHub Issues](https://github.com/TANG617/RunBuoy/issues) without including private run data or credentials. Security reports must use [private vulnerability reporting](https://github.com/TANG617/RunBuoy/security/advisories/new).

Last updated: August 7, 2026.
