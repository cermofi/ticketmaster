#!/usr/bin/env bash
# Fail when production-like deploy would run with unsafe defaults.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

APP_SECRET="${APP_SECRET:-dev-ticketmaster-secret-change-me}"
APP_DEBUG="${APP_DEBUG:-false}"
ALLOW_SEED_DEV="${ALLOW_SEED_DEV:-false}"
ALLOW_DEV_SSO="${ALLOW_DEV_SSO:-false}"
TICKETMASTER_DEV_PASSWORD="${TICKETMASTER_DEV_PASSWORD:-ChangeMe123!}"

errors=()

case "${APP_SECRET}" in
  dev-change-me|dev-ticketmaster-secret-change-me)
    errors+=("APP_SECRET is still a default dev value")
    ;;
esac

if [[ "${APP_DEBUG}" == "true" || "${APP_DEBUG}" == "1" || "${APP_DEBUG}" == "yes" || "${APP_DEBUG}" == "on" ]]; then
  errors+=("APP_DEBUG is enabled")
fi

if [[ "${ALLOW_SEED_DEV}" == "true" || "${ALLOW_SEED_DEV}" == "1" || "${ALLOW_SEED_DEV}" == "yes" || "${ALLOW_SEED_DEV}" == "on" ]]; then
  errors+=("ALLOW_SEED_DEV is enabled")
fi

if [[ "${ALLOW_DEV_SSO}" == "true" || "${ALLOW_DEV_SSO}" == "1" || "${ALLOW_DEV_SSO}" == "yes" || "${ALLOW_DEV_SSO}" == "on" ]]; then
  errors+=("ALLOW_DEV_SSO is enabled")
fi

if [[ "${TICKETMASTER_DEV_PASSWORD}" == "ChangeMe123!" ]]; then
  errors+=("TICKETMASTER_DEV_PASSWORD is still the default dev value")
fi

if [[ ${#errors[@]} -gt 0 ]]; then
  echo "error: unsafe production configuration detected:" >&2
  for item in "${errors[@]}"; do
    echo "  - ${item}" >&2
  done
  exit 1
fi

echo "Production configuration checks passed."
