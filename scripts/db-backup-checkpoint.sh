#!/usr/bin/env bash
# Create a pre-migrate PostgreSQL backup checkpoint (used before risky migrations).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${ROOT}/.deploy/backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_FILE="${BACKUP_DIR}/pre-migrate-${STAMP}.sql"

mkdir -p "${BACKUP_DIR}"

cd "${ROOT}"
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-ticketmaster}" "${POSTGRES_DB:-ticketmaster}" > "${BACKUP_FILE}"

echo "${BACKUP_FILE}"
