#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${SMOKE_CHECK_BASE_URL:-https://ticketmaster.cermofi.cz}"

echo "Running smoke check against ${BASE_URL}"
export SMOKE_CHECK_BASE_URL="${BASE_URL}"

if [[ -z "${SMOKE_ALLOW_AUTH:-}" ]]; then
  unset SMOKE_CHECK_EMAIL SMOKE_CHECK_PASSWORD
fi

cd "${ROOT}/backend"
if command -v ticketmaster-cli >/dev/null 2>&1; then
  ticketmaster-cli smoke check
elif command -v docker >/dev/null 2>&1 && docker compose -f "${ROOT}/docker-compose.yml" ps -q api >/dev/null 2>&1; then
  docker compose -f "${ROOT}/docker-compose.yml" exec -T \
    -e SMOKE_CHECK_BASE_URL="${SMOKE_CHECK_BASE_URL}" \
    api ticketmaster-cli smoke check
else
  python -m ticketmaster.cli.main smoke check
fi

echo "Smoke check passed."
