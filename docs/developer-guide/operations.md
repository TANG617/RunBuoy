# Server operations

## Probes and startup

`GET /healthz` is a liveness-only probe. It does not touch PostgreSQL and stays
usable while a dependency is unavailable. `GET /readyz` is the traffic and
deployment gate. It returns `503 not_ready` unless all required checks pass:

- PostgreSQL accepts a query;
- the single current Alembic revision equals the repository head;
- at least one `outbox-worker` heartbeat is healthy and no older than
  `WORKER_HEARTBEAT_MAX_AGE_SECONDS` (90 seconds by default);
- required configuration is structurally valid.

Multiple worker rows are intentional. One failed worker remains visible as a
count while another fresh healthy worker keeps the service ready. Responses do
not include instance identifiers, connection strings, credentials, or config
values. Set `WORKER_HEARTBEAT_REQUIRED=false` only for an explicitly disposable
maintenance process; production should keep the default.

The production Compose health check, Caddy dependency, deploy script, and
post-deploy workflow all use `/readyz`. Load balancers should do the same.

## Metrics, logs, and alerts

`GET /metrics` uses Prometheus text exposition. The bundled production Caddy
returns 404 for this path; scrape it over the private Compose/API network or an
authenticated monitoring sidecar. A custom ingress must enforce the same
private boundary. Labels are deliberately bounded to HTTP method, route
template, status/reason class, outbox state, cleanup table, and sync outcome.
Run titles, safe messages, machine/device/workspace/user identifiers, tokens,
and arbitrary APNs reasons are never labels.

The main metric families cover HTTP count/latency and rate-limit rejection,
outbox state/oldest age, APNs class/latency/invalid-token count, active Live
Activity bindings, worker age/status, cleanup rows, and read/sync outcomes.
Alert at minimum on:

- `/readyz` failing for two probe intervals;
- `runbuoy_worker_heartbeat_age_seconds` approaching the configured maximum;
- oldest pending outbox age growing continuously or failed/expired pushes
  increasing;
- invalid-token or APNs authentication/transient failures increasing;
- the backup systemd unit exiting nonzero or a successful backup becoming old.

Each API request emits one JSON object with `request_id`, method, route template,
status, and latency. A syntactically safe caller-provided `X-Request-ID` is
one-way normalized before use; malformed values are replaced. Headers, query
strings, bodies, QR/pairing material, APNs
tokens, and user payloads are not logged. Search by request ID rather than
turning on payload logging during an incident.

## Backups and off-host copies

Install `infra/backup-runbuoy`, `infra/runbuoy-backup.service`, and
`infra/runbuoy-backup.timer`. The root-only job uses a non-blocking lock and an
atomic directory rename. Each timestamped backup contains:

- a validated custom-format PostgreSQL dump;
- a root-only archive of `/etc/runbuoy`;
- `manifest.json` with schema version, PostgreSQL version, Alembic revision,
  sizes, and SHA-256 values;
- `SHA256SUMS`.

Local retention defaults to 14 days. A local-only backup does not cover host
loss. To enable encrypted off-host restic copies, put the repository locator
and password in separate root-owned `0600` files, then configure paths only in
`/etc/runbuoy/backup.env`:

```dotenv
RUNBUOY_RESTIC_REPOSITORY_FILE=/etc/runbuoy/restic-repository
RUNBUOY_RESTIC_PASSWORD_FILE=/etc/runbuoy/restic-password
```

The password is passed through `RESTIC_PASSWORD_FILE`, never a command-line
argument. A restic failure makes the systemd job fail and writes a
`runbuoy-backup` journal event; monitoring must alert on that unit failure.

## Restore drill and disaster recovery

Practice against a disposable database and config directory first. The tool
validates the manifest, checksums, dump catalog, archive paths, migration
compatibility, and PostgreSQL major version before replacing anything:

```bash
sudo infra/restore-runbuoy \
  --backup /var/backups/runbuoy/20260807T023000Z \
  --target-database runbuoy_restore_drill \
  --target-config-root /tmp/runbuoy-restore-drill \
  --expected-revision d001_sync \
  --confirm 'RESTORE DISPOSABLE'
```

The CI-equivalent round trip is:

```bash
docker compose --env-file infra/.env.example -f infra/docker-compose.yml up -d --build
./scripts/backup_restore_smoke.sh
```

Production restore is intentionally destructive and refuses to run while any
Compose `api` or `worker` instance is running. After separately preserving the
damaged state, stop those services and use the exact database/config targets
and confirmation:

```bash
docker compose -p runbuoy --env-file /etc/runbuoy/runbuoy.env \
  -f infra/docker-compose.yml -f infra/docker-compose.prod.yml stop api worker
sudo RUNBUOY_EXPECTED_MIGRATION_REVISION=d001_sync infra/restore-runbuoy \
  --production \
  --backup /var/backups/runbuoy/20260807T023000Z \
  --target-database runbuoy \
  --target-config-root /etc/runbuoy \
  --confirm 'RESTORE RUNBUOY PRODUCTION'
```

An existing config directory is retained beside the restored directory with a
`pre-restore` timestamp. Apply the release migration, start worker and API,
then require `/readyz` before restoring ingress traffic. Never use production
as the first restore test.

## Bounded load smoke

The lifecycle smoke performs device bootstrap, pairing, Run registration,
heartbeat, progress, and terminal events without registering push tokens:

```bash
uv run --project server python scripts/load_smoke.py --runs 6 --concurrency 3
```

It defaults to localhost and caps runs/concurrency. A non-loopback URL is
refused unless the operator explicitly adds `--confirm-remote 'RUNBUOY LOAD'`.
Choose a disposable mock-APNs deployment; the script must not be aimed at
production as routine monitoring.
