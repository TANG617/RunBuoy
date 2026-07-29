#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api_url="${RUNBUOY_E2E_URL:-http://127.0.0.1:8000}"
compose_file="$repo_root/infra/docker-compose.yml"
compose_env="$repo_root/infra/.env.example"
test_root="$(mktemp -d /tmp/runbuoy-e2e.XXXXXX)"
pair_log="$test_root/pair.jsonl"
long_log="$test_root/long.jsonl"

cleanup() {
  if [[ -n "${pair_pid:-}" ]] && kill -0 "$pair_pid" 2>/dev/null; then
    kill "$pair_pid" 2>/dev/null || true
  fi
  if [[ -n "${run_pid:-}" ]] && kill -0 "$run_pid" 2>/dev/null; then
    kill "$run_pid" 2>/dev/null || true
  fi
  rm -rf "$test_root"
}
trap cleanup EXIT

export XDG_CONFIG_HOME="$test_root/config"
export XDG_DATA_HOME="$test_root/data"
export XDG_STATE_HOME="$test_root/state"
export XDG_CACHE_HOME="$test_root/cache"
export RUNBUOY_DISABLE_KEYRING=1

rb=(uv run --project "$repo_root/cli" runbuoy)
compose=(docker compose --env-file "$compose_env" -f "$compose_file")

json_value() {
  local expression="$1"
  local input_file="$2"
  python3 - "$expression" "$input_file" <<'PY'
import json
import sys

expression, path = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    value = json.loads(handle.readline())
print(eval(expression, {"__builtins__": {}}, {"value": value}))
PY
}

wait_for() {
  local description="$1"
  local command="$2"
  local attempts="${3:-60}"
  for ((index = 0; index < attempts; index += 1)); do
    if eval "$command"; then
      return 0
    fi
    sleep 0.5
  done
  echo "timed out waiting for: $description" >&2
  return 1
}

db_scalar() {
  local sql="$1"
  "${compose[@]}" exec -T db \
    psql -U "${POSTGRES_USER:-runbuoy}" -d "${POSTGRES_DB:-runbuoy}" \
    -Atc "$sql"
}

wait_for "RunBuoy API" \
  "curl --silent --fail '$api_url/healthz' >/dev/null" \
  120

bootstrap_file="$test_root/bootstrap.json"
curl --silent --fail \
  -X POST "$api_url/v1/devices/bootstrap" \
  -H 'Content-Type: application/json' \
  -d '{"installation_id":"e2e-installation","app_version":"0.1.0","os_version":"18.0"}' \
  >"$bootstrap_file"
device_id="$(json_value 'value["device_id"]' "$bootstrap_file")"
device_credential="$(json_value 'value["credential"]' "$bootstrap_file")"

"${rb[@]}" config set --server-url "$api_url" --machine-name "E2E Machine" >/dev/null
"${rb[@]}" device pair --json >"$pair_log" &
pair_pid=$!
wait_for "CLI pairing QR before poll" \
  "test -s '$pair_log'" \
  30
pair_session="$(json_value 'value["pairing"]["pairing_session_id"]' "$pair_log")"
pair_challenge="$(json_value 'value["pairing"]["challenge"]' "$pair_log")"

curl --silent --fail \
  -X POST "$api_url/v1/pairing-sessions/$pair_session/claim" \
  -H "Authorization: Bearer $device_credential" \
  -H 'Content-Type: application/json' \
  -d "{\"challenge\":\"$pair_challenge\"}" \
  >/dev/null
wait "$pair_pid"
unset pair_pid

curl --silent --fail \
  -X PUT "$api_url/v1/devices/$device_id/notification-token" \
  -H "Authorization: Bearer $device_credential" \
  -H 'Content-Type: application/json' \
  -d '{"token":"e2e_notification_token_0123456789","generation":1}' \
  >/dev/null
curl --silent --fail \
  -X PUT "$api_url/v1/devices/$device_id/push-to-start-token" \
  -H "Authorization: Bearer $device_credential" \
  -H 'Content-Type: application/json' \
  -d '{"token":"e2e_push_to_start_token_0123456789","generation":1}' \
  >/dev/null

"${rb[@]}" run --json --wait -- sleep 8 >"$long_log" &
run_pid=$!
wait_for "long Run ID" \
  "test -s '$long_log'" \
  30
long_run_id="$(json_value 'value["run_id"]' "$long_log")"

wait_for "Live Activity start payload" \
  "[[ \$(db_scalar \"SELECT count(*) FROM push_attempts pa JOIN push_outbox po ON po.id = pa.outbox_id WHERE po.run_id = '$long_run_id' AND pa.request_payload->'aps'->>'event' = 'start'\") -ge 1 ]]" \
  30

curl --silent --fail \
  -X POST "$api_url/v1/devices/$device_id/activity-sync" \
  -H "Authorization: Bearer $device_credential" \
  -H 'Content-Type: application/json' \
  -d "{\"activities\":[{\"activity_id\":\"e2e-$long_run_id\",\"run_id\":\"$long_run_id\",\"update_token\":\"e2e_update_token_0123456789\",\"token_generation\":1,\"state\":\"active\",\"last_sequence\":3}]}" \
  >/dev/null

wait "$run_pid"
unset run_pid
wait_for "Live Activity end payload" \
  "[[ \$(db_scalar \"SELECT count(*) FROM push_attempts pa JOIN push_outbox po ON po.id = pa.outbox_id WHERE po.run_id = '$long_run_id' AND pa.request_payload->'aps'->>'event' = 'end'\") -ge 1 ]]" \
  30

detail_file="$test_root/detail.json"
curl --silent --fail \
  "$api_url/v1/runs/$long_run_id" \
  -H "Authorization: Bearer $device_credential" \
  >"$detail_file"
python3 - "$detail_file" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
run = value.get("run", value)
assert run["execution_status"] == "SUCCEEDED", run
assert run["exit_code"] == 0, run
assert int(run.get("sequence", run.get("last_seq", 0))) >= 4, run
PY

regex_log="$test_root/regex.jsonl"
"${rb[@]}" run \
  --json \
  --wait \
  --progress regex \
  --pattern '^PROGRESS: ([0-9]+)/([0-9]+)$' \
  -- sh -c 'printf "PROGRESS: 1/3\nPROGRESS: 2/3\nPROGRESS: 3/3\n"' \
  >"$regex_log"
regex_run_id="$(json_value 'value["run_id"]' "$regex_log")"
regex_detail="$test_root/regex-detail.json"
curl --silent --fail \
  "$api_url/v1/runs/$regex_run_id" \
  -H "Authorization: Bearer $device_credential" \
  >"$regex_detail"
python3 - "$regex_detail" <<'PY'
import json
import sys

value = json.load(open(sys.argv[1], encoding="utf-8"))
run = value.get("run", value)
assert run["progress"]["fraction"] == 1.0, run
PY

short_success="$test_root/short-success.jsonl"
"${rb[@]}" run --json --wait -- true >"$short_success"
short_success_id="$(json_value 'value["run_id"]' "$short_success")"
sleep 1
[[ "$(db_scalar "SELECT count(*) FROM push_attempts pa JOIN push_outbox po ON po.id = pa.outbox_id WHERE po.run_id = '$short_success_id' AND pa.request_payload->'aps'->>'event' = 'start'")" == "0" ]]

short_failure="$test_root/short-failure.jsonl"
set +e
"${rb[@]}" run --json --wait -- sh -c 'exit 3' >"$short_failure"
short_failure_status=$?
set -e
[[ "$short_failure_status" == "3" ]]
short_failure_id="$(json_value 'value["run_id"]' "$short_failure")"
wait_for "short failure notification" \
  "[[ \$(db_scalar \"SELECT count(*) FROM notifications WHERE run_id = '$short_failure_id' AND level = 'error'\") -ge 1 ]]" \
  30

python3 - "$api_url" <<'PY'
import json
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1] + "/openapi.json") as response:
    paths = "\n".join(json.load(response)["paths"]).lower()
for fragment in ("/cancel", "/retry", "/input", "/commands", "/execute", "/signal", "/approve", "/keys"):
    assert fragment not in paths, fragment
PY

privacy_violations="$(db_scalar "SELECT count(*) FROM run_events WHERE payload::text ~* '\"(argv|cwd|env|stdout|stderr|stdin|token|secret|command)\"'")"
[[ "$privacy_violations" == "0" ]]

echo "RunBuoy E2E smoke: PASS"
echo "- CLI QR pairing and scoped credential exchange"
echo "- long Run Live Activity start/end through mock APNs"
echo "- regex progress reaches 100%"
echo "- short success stays silent and short failure notifies"
echo "- read projection is terminal and accurate"
echo "- no remote-control OpenAPI paths or sensitive event keys"
