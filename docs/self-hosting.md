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

Set `RUNBUOY_REGION` to `global` or `cn` on each deployment. A hosted client
and every Machine paired to it must use the same value; databases, credentials,
pairing challenges, and user data are not synchronized across regions.

## Secrets

Generate independent values for database credentials, bearer-token hashing,
and token encryption. Mount the APNs `.p8` key as a file from a secret store.
Do not put secrets in `.env.example`, images, CI logs, Compose command lines,
or repository files.

## Retention and operations

- Prune expired pairing sessions and audit logs according to policy.
- Delete explicitly shared log tails after 24 hours.
- Keep append-only Run events only as long as operationally necessary.
- Monitor outbox backlog, retries, permanent APNs failures, API latency, and
  PostgreSQL capacity without logging payload secrets.
- Treat APNs 410 as token invalidation.
- Restore into a private environment and test migration plus encryption-key
  access before declaring a backup valid.

The Server must never be extended with a Machine command channel, inbound
Machine port, tunnel, WebSocket control route, or remote execution endpoint.
