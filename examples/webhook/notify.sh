#!/bin/sh
set -eu

: "${RUNBUOY_HOOK_ID:?set RUNBUOY_HOOK_ID}"
: "${RUNBUOY_HOOK_SECRET:?set RUNBUOY_HOOK_SECRET}"
: "${RUNBUOY_SERVER_URL:?set RUNBUOY_SERVER_URL}"

curl --fail-with-body \
  -H "Authorization: Bearer ${RUNBUOY_HOOK_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{"title":"Build completed","body":"Release build succeeded","level":"success"}' \
  "${RUNBUOY_SERVER_URL}/v1/hooks/${RUNBUOY_HOOK_ID}/notifications"
