# Self-hosting

## Requirements

- Docker Engine with Compose
- An HTTPS hostname and reverse proxy/load balancer
- PostgreSQL storage and backups
- A random database password and token encryption key
- Optional Apple APNs credentials for production push

## Start in mock mode

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

The API and outbox worker are separate processes over the same PostgreSQL
database. Redis is not required. Apply Alembic migrations before serving.

Never expose PostgreSQL publicly. Terminate TLS at a trusted ingress and pass
only the API port. Back up PostgreSQL and encryption-key material together;
without the encryption key, restored APNs tokens are intentionally unusable.

The Server accepts `RUNBUOY_REGION=global|cn`, and every client paired to a
deployment must use the same value; databases, credentials, pairing challenges,
and user data are not synchronized across regions. The current iOS app only
exposes `global` and normalizes legacy `cn` values to Global, so an end-to-end
self-hosted deployment should currently use `global` unless the App source is
also changed and rebuilt to implement a distinct region.

## Secrets

Generate independent values for database credentials, bearer-token hashing,
and token encryption. Mount the APNs `.p8` key as a file from a secret store.
Do not put secrets in `.env.example`, images, CI logs, Compose command lines,
or repository files.

## Retention and operations

- The current worker deletes notifications only when their explicit
  `expires_at` has passed.
- It deletes terminal Run events and clears explicitly shared log tails after
  `EVENT_RETENTION_HOURS` (24 hours by default).
- It marks remote-start Live Activity placeholders expired after
  `LIVE_ACTIVITY_PENDING_TTL_SECONDS` (300 seconds by default).
- Current cleanup does not delete Run snapshots, expired pairing-session rows,
  audit logs, or notifications without `expires_at`; add an operator policy if
  those tables require age-based retention.
- Monitor outbox backlog, retries, permanent APNs failures, API latency, and
  PostgreSQL capacity without logging payload secrets.
- Treat APNs 410 as token invalidation.
- Restore into a private environment and test migration plus encryption-key
  access before declaring a backup valid.

The Server must never be extended with a Machine command channel, inbound
Machine port, tunnel, WebSocket control route, or remote execution endpoint.
