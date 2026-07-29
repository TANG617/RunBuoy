# Self-hosting

RunBuoy Server can run on your own infrastructure.

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

## Production considerations

- Do not expose PostgreSQL to the public internet.
- Terminate TLS at a trusted ingress and forward only the API port.
- Generate independent database, credential-hashing, and token-encryption secrets.
- Store the APNs `.p8` file in a secret store.
- Back up the database and token-encryption key together.
- Delete explicitly shared log snippets within 24 hours.

See [docs/self-hosting.md](https://github.com/TANG617/RunBuoy/blob/main/docs/self-hosting.md) for the complete deployment guide.
