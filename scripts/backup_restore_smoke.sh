#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repo_root/infra/docker-compose.yml"
compose_env="${RUNBUOY_COMPOSE_ENV:-$repo_root/infra/.env.example}"
smoke_root="$(mktemp -d /tmp/runbuoy-backup-restore.XXXXXX)"
database_name="runbuoy_restore_smoke_$RANDOM"
api_container="runbuoy-restore-smoke-api-$$"
worker_container="runbuoy-restore-smoke-worker-$$"
api_port="${RUNBUOY_RESTORE_SMOKE_PORT:-18001}"
compose=(docker compose --env-file "$compose_env" -f "$compose_file")
db_container="${RUNBUOY_DB_CONTAINER:-$("${compose[@]}" ps -q db)}"
db_user="${POSTGRES_USER:-runbuoy}"
db_password="${POSTGRES_PASSWORD:-replace-with-a-long-random-password}"
database_url="postgresql+psycopg://$db_user:$db_password@db:5432/$database_name"

cleanup() {
  docker rm -f "$api_container" "$worker_container" >/dev/null 2>&1 || true
  if [[ -n "$db_container" ]]; then
    docker exec "$db_container" dropdb \
      --username "$db_user" --if-exists --force "$database_name" >/dev/null 2>&1 || true
  fi
  rm -r -- "$smoke_root"
}
trap cleanup EXIT

[[ -n "$db_container" ]] || {
  echo "backup/restore smoke requires the Compose database service" >&2
  exit 2
}
docker inspect "$db_container" >/dev/null
docker exec "$db_container" dropdb \
  --username "$db_user" --if-exists --force "$database_name" >/dev/null
docker exec "$db_container" createdb --username "$db_user" "$database_name"

"${compose[@]}" exec -T \
  -e "DATABASE_URL=$database_url" \
  api alembic upgrade head
docker exec "$db_container" psql \
  --username "$db_user" --dbname "$database_name" \
  --command 'CREATE TABLE restore_smoke_marker (value text PRIMARY KEY)' \
  --command "INSERT INTO restore_smoke_marker VALUES ('backup-round-trip')" >/dev/null

source_config="$smoke_root/source-config"
mkdir -m 0700 "$source_config"
printf '%s\n' 'synthetic restore smoke config' >"$source_config/runbuoy.env"
chmod 0600 "$source_config/runbuoy.env"

RUNBUOY_ALLOW_NON_ROOT=1 \
RUNBUOY_BACKUP_ROOT="$smoke_root/backups" \
RUNBUOY_CONFIG_ROOT="$source_config" \
RUNBUOY_DB_CONTAINER="$db_container" \
RUNBUOY_DATABASE_USER="$db_user" \
RUNBUOY_DATABASE_NAME="$database_name" \
RUNBUOY_BACKUP_RETENTION_DAYS=1 \
  "$repo_root/infra/backup-runbuoy"

backup_directory="$(find "$smoke_root/backups" -mindepth 1 -maxdepth 1 -type d -name '20??????T??????Z' -print -quit)"
[[ -n "$backup_directory" ]]

tampered_backup="$smoke_root/tampered-backup"
cp -a "$backup_directory" "$tampered_backup"
printf '%s' 'tampered' >>"$tampered_backup/runbuoy.pg_dump"
set +e
RUNBUOY_ALLOW_NON_ROOT=1 \
RUNBUOY_DB_CONTAINER="$db_container" \
RUNBUOY_DATABASE_USER="$db_user" \
  "$repo_root/infra/restore-runbuoy" \
  --backup "$tampered_backup" \
  --target-database runbuoy_restore_tampered \
  --target-config-root "$smoke_root/tampered-config" \
  --expected-revision d001_sync \
  --confirm 'RESTORE DISPOSABLE' >/dev/null 2>&1
tampered_status=$?
set -e
[[ "$tampered_status" != "0" ]] || {
  echo "restore accepted a tampered backup" >&2
  exit 1
}

restored_config="$smoke_root/restored-config"
RUNBUOY_ALLOW_NON_ROOT=1 \
RUNBUOY_DB_CONTAINER="$db_container" \
RUNBUOY_DATABASE_USER="$db_user" \
  "$repo_root/infra/restore-runbuoy" \
  --backup "$backup_directory" \
  --target-database "$database_name" \
  --target-config-root "$restored_config" \
  --expected-revision d001_sync \
  --confirm 'RESTORE DISPOSABLE'

[[ "$(docker exec "$db_container" psql --username "$db_user" --dbname "$database_name" --tuples-only --no-align --command 'SELECT value FROM restore_smoke_marker')" == "backup-round-trip" ]]
[[ "$(docker exec "$db_container" psql --username "$db_user" --dbname "$database_name" --tuples-only --no-align --command 'SELECT version_num FROM alembic_version')" == "d001_sync" ]]
cmp "$source_config/runbuoy.env" "$restored_config/runbuoy.env"

"${compose[@]}" run -d --no-deps \
  --name "$worker_container" \
  -e "DATABASE_URL=$database_url" \
  -e APNS_MODE=mock \
  -e RUNBUOY_WORKER_INSTANCE_ID=restore-smoke \
  worker >/dev/null
"${compose[@]}" run -d --no-deps \
  --name "$api_container" \
  -p "127.0.0.1:$api_port:8000" \
  -e "DATABASE_URL=$database_url" \
  -e APNS_MODE=mock \
  api uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log >/dev/null

ready=0
for _attempt in $(seq 1 60); do
  if response="$(curl --fail --silent --show-error "http://127.0.0.1:$api_port/readyz" 2>/dev/null)" && \
    [[ "$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<<"$response")" == "ready" ]]; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == "1" ]] || {
  docker logs "$worker_container" >&2 || true
  docker logs "$api_container" >&2 || true
  echo "restored API did not become ready" >&2
  exit 1
}

echo "RunBuoy backup/restore smoke: PASS"
echo "- manifest, checksums, migration revision, database marker, config, worker, and /readyz"
