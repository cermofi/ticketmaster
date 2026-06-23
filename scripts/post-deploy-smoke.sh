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
ticketmaster-cli smoke check

echo "Smoke check passed."
