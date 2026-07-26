# Privacy boundary

Remote payloads may contain a safe title, machine display name, state, progress, phase, safe
message, timestamps, exit code, and health. They must not contain complete argv, cwd,
environment, source or file contents, stdin, stdout/stderr, terminal frames, or credentials.

Keep log sharing disabled unless the user explicitly requests `--share-log-tail 1..100`.
Redaction is defense in depth, not permission to publish sensitive output. Avoid putting
customer names, paths, URLs with query secrets, tokens, or command flags in titles and messages.

RunBuoy is one-way and read-only: Machine → Server → iPhone. Never create server-to-machine
polling, sockets, command queues, signals, input, cancellation, retry, or approval.
