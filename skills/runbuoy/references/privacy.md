# Privacy boundary

Remote payloads may contain a sanitized title, machine display name, execution state, progress,
phase, structured message, attention message, timestamps, exit code, health, and explicitly
shared log tail.

Important: every record accepted by `--progress lines --match ...` or `--progress regex
--pattern ...` becomes the latest sanitized message and may be remotely visible. Structured
`progress(..., message=...)`, `phase`, `message`, and `attention` may also be remote. Sanitization
is defense in depth, not permission to disclose content.

Do not place complete argv, cwd, environment, source/file contents, user input, paths, customer
names, URL queries, tokens, credentials, or arbitrary stdout/stderr in remotely visible fields.
Keep `--share-log-tail` disabled unless the user explicitly asks to share a bounded tail.

Local `runbuoy logs` reads the full PTY log without uploading it. `attach` and `cancel` are also
local-only.

RunBuoy is one-way and read-only: Machine → Server → iPhone. A phone or server cannot start,
cancel, retry, approve, provide input, attach, or control the machine.
