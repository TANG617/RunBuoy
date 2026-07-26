# Contributing

RunBuoy accepts changes that preserve its one-way boundary:
`Machine → Server → iPhone`.

Before opening a pull request:

1. Read ADR 0001, `docs/security.md`, and `docs/protocol.md`.
2. Keep full execution data local by default.
3. Add tests for protocol, scope, ordering, retries, and privacy behavior.
4. Run the commands in `docs/development.md`.
5. Update OpenAPI, JSON Schema, fixtures, and both Swift/Python models together.
6. Update provenance when reusing third-party code.

Do not propose a remote command, Machine inbox, terminal stream, input,
cancel/retry/signal, approval, tunnel, WebSocket control, WebView terminal, or
mobile mutation action. Local-only CLI control remains acceptable when it
cannot be reached through the Server or iPhone.

Never commit tokens, `.p8` files, provisioning profiles, `.env`, databases, or
logs. Use mock APNs and synthetic fixture tokens in tests.
