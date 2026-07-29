# Privacy

RunBuoy is designed around “do not upload by default.” It synchronizes only the limited data required to show run status on an iPhone.

## Data synchronized by default

- Machine identifier and display name
- Safe title
- Run status, phase, and structured progress
- Safe message, timestamps, and exit code
- Device tokens required for notifications and Live Activities

## Data kept on the computer by default

- Complete commands and arguments
- Working directory and environment variables
- Source code, file contents, and user input
- stdout, stderr, and terminal frames
- API keys, SSH keys, and cloud credentials
- Full logs

## Optional log snippet

Only an explicit `--share-log-tail 1..100` option uploads a bounded trailing log snippet. Before upload, RunBuoy removes ANSI control sequences, limits size, and redacts credential patterns. iOS labels the snippet clearly, and the server retains it for at most 24 hours.

## Credentials and device tokens

Long-lived credentials never appear in URLs, QR codes, or ordinary logs. The server stores credential hashes and encrypts APNs and Live Activity tokens.

## Website

This is a static website and does not load advertising or third-party analytics by default. GitHub Pages may record access and security logs according to its service policy.

## Self-hosting

Self-hosted operators choose their server location, retention, and logging policies. They are responsible for protecting PostgreSQL, encryption keys, APNs credentials, and backups.

## Contact and updates

RunBuoy is open source. The authoritative privacy implementation and change history are in the [GitHub repository](https://github.com/TANG617/RunBuoy). Questions can be filed through [Issues](https://github.com/TANG617/RunBuoy/issues).

Last updated: July 28, 2026.
