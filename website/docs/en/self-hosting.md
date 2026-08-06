---
description: Deploy a private RunBuoy Server and point both the CLI and a custom iOS build to it before pairing.
---

# Self-hosting

RunBuoy Server can run on your own infrastructure.

:::warning Choose one Server before pairing
The CLI and your own iOS build must point to the same RunBuoy Server before pairing. Configure the CLI with `runbuoy config set --server-url`, and build the app with `RUNBUOY_API_BASE_URL` set to the same HTTPS address. An existing Machine cannot be moved to another Server after pairing. The current official end-to-end flow uses the `Global` region.
:::

## Requirements

- Docker Engine and Docker Compose
- An HTTPS domain and a reverse proxy or load balancer
- PostgreSQL with reliable backups
- Random database password, credential pepper, and token-encryption key
- Apple APNs credentials for production push delivery

## Mock mode

Run this from the repository root:

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

Mock APNs requires no Apple credentials. It records deterministic push payloads and is suitable for development and end-to-end testing.

## Configure the CLI

```bash
runbuoy config set --server-url https://runbuoy.example.com
runbuoy doctor
```

Set the same address in your custom iOS build:

```text
RUNBUOY_API_BASE_URL=https://runbuoy.example.com
```

The current app has no user-facing field for a self-hosted Server URL, so changing the CLI alone is not sufficient for self-hosted pairing.

## Production considerations

- Do not expose PostgreSQL to the public internet.
- Terminate TLS at a trusted ingress and forward only the API port.
- Generate independent database, credential-hashing, and token-encryption secrets.
- Store the APNs `.p8` file in a secret store.
- Back up the database and token-encryption key together.
- Delete explicitly shared log snippets within 24 hours.

See [docs/developer-guide/self-hosting.md](https://github.com/TANG617/RunBuoy/blob/main/docs/developer-guide/self-hosting.md) for the complete deployment guide.
