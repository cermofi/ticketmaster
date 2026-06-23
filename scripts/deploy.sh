#!/usr/bin/env bash
# Production deploy: pull → (risky-migration backup) → migrate → build → mandatory smoke gate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ROLLBACK_DIR="${ROOT}/.deploy"
ROLLBACK_FILE="${ROLLBACK_DIR}/last-good-rev"
SMOKE_BASE_URL="${SMOKE_CHECK_BASE_URL:-https://ticketmaster.cermofi.cz}"
COMPOSE=(docker compose -f "${ROOT}/docker-compose.yml")
PRODUCTION="${TM_ENV:-production}"

mkdir -p "${ROLLBACK_DIR}"

on_fail() {
  local code=$?
  echo ""
  echo "=== DEPLOY FAILED (exit ${code}) — rollback instructions ==="
  echo "  cd ${ROOT}"
  echo "  git checkout ${PRE_DEPLOY_REV}"
  echo "  ${COMPOSE[*]} up -d --build"
  echo "  ${COMPOSE[*]} exec -T api ticketmaster-cli db migrate"
  echo "  curl -fsS ${SMOKE_BASE_URL}/api/health"
  echo "  curl -fsS ${SMOKE_BASE_URL}/api/ready"
  echo "  SMOKE_CHECK_BASE_URL=${SMOKE_BASE_URL} bash ${ROOT}/scripts/post-deploy-smoke.sh"
  if [[ -n "${BACKUP_FILE:-}" && -f "${BACKUP_FILE}" ]]; then
    echo "  # DB restore if risky migration ran:"
    echo "  docker compose exec -T db psql -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\" < ${BACKUP_FILE}"
  fi
  if [[ -n "${ROLLBACK_ARTIFACT:-}" && -f "${ROLLBACK_ARTIFACT}" ]]; then
    echo "  # Full artifact: ${ROLLBACK_ARTIFACT}"
  fi
  echo "=============================================================="
  exit "${code}"
}
trap on_fail ERR

save_rollback_point() {
  local rev
  rev="$(git rev-parse HEAD)"
  echo "${rev}" > "${ROLLBACK_FILE}"
  echo "${rev}"
}

PRE_DEPLOY_REV="$(save_rollback_point)"
echo "Rollback point saved: ${PRE_DEPLOY_REV}"

if [[ "${PRODUCTION}" == "production" ]]; then
  echo "==> Validating production configuration"
  bash "${ROOT}/scripts/check-production-config.sh"
fi

echo "==> Pulling latest main (ff-only)"
git pull --ff-only origin main

echo "==> Building API image (migration/smoke tooling)"
"${COMPOSE[@]}" build api

echo "==> Inspecting pending migrations"
MIGRATION_PLAN="$("${COMPOSE[@]}" run --rm -T api ticketmaster-cli db plan)"
echo "${MIGRATION_PLAN}"

RISKY_PENDING="$(echo "${MIGRATION_PLAN}" | python3 -c "import json,sys; print(','.join(json.load(sys.stdin).get('risky_pending',[])))")"
BACKUP_FILE=""
ROLLBACK_ARTIFACT=""

if [[ -n "${RISKY_PENDING}" ]]; then
  echo "==> Risky migrations pending: ${RISKY_PENDING}"
  if [[ "${PRODUCTION}" == "production" && "${MIGRATE_CONFIRM:-}" != "1" ]]; then
    echo "error: set MIGRATE_CONFIRM=1 to apply risky migrations in production" >&2
    exit 1
  fi
  if [[ "${SKIP_MIGRATION_BACKUP:-}" != "1" ]]; then
    echo "==> Creating pre-migrate DB backup checkpoint"
    BACKUP_FILE="$(bash "${ROOT}/scripts/db-backup-checkpoint.sh")"
    echo "Backup saved: ${BACKUP_FILE}"
  else
    echo "warning: SKIP_MIGRATION_BACKUP=1 — no DB backup created" >&2
  fi
  ROLLBACK_ARTIFACT="${ROLLBACK_DIR}/rollback-$(date -u +%Y%m%dT%H%M%SZ).md"
  {
    echo "# TicketMaster deploy rollback"
    echo ""
    echo "- Saved git revision: \`${PRE_DEPLOY_REV}\`"
    echo "- Risky migrations: ${RISKY_PENDING}"
    echo "- Pre-migrate backup: \`${BACKUP_FILE:-none}\`"
    echo ""
    echo "## Roll back"
    echo ""
    echo '```bash'
    echo "cd ${ROOT}"
    echo "git checkout ${PRE_DEPLOY_REV}"
    echo "${COMPOSE[*]} up -d --build"
    echo "${COMPOSE[*]} exec -T api ticketmaster-cli db migrate"
    echo "SMOKE_CHECK_BASE_URL=${SMOKE_BASE_URL} bash ${ROOT}/scripts/post-deploy-smoke.sh"
    if [[ -n "${BACKUP_FILE:-}" ]]; then
      echo "docker compose exec -T db psql -U \"\$POSTGRES_USER\" \"\$POSTGRES_DB\" < ${BACKUP_FILE}"
    fi
    echo '```'
  } > "${ROLLBACK_ARTIFACT}"
  echo "Rollback artifact: ${ROLLBACK_ARTIFACT}"
fi

echo "==> Running database migrations"
if [[ -n "${RISKY_PENDING}" && "${PRODUCTION}" == "production" ]]; then
  MIGRATE_CONFIRM=1 "${COMPOSE[@]}" run --rm -T -e MIGRATE_CONFIRM=1 api ticketmaster-cli db migrate --confirm-risky
else
  "${COMPOSE[@]}" run --rm -T api ticketmaster-cli db migrate
fi

echo "==> Building and restarting changed services"
HEAD_REV="$(git rev-parse HEAD)"
if [ "$PRE_DEPLOY_REV" != "$HEAD_REV" ] || git diff --name-only "${PRE_DEPLOY_REV}" HEAD | grep -qE '^(backend/|frontend/|docs-site/|docker-compose)'; then
  "${COMPOSE[@]}" up -d --build
else
  echo "No service image changes detected; restarting api and frontend only"
  "${COMPOSE[@]}" up -d api frontend
fi

echo "==> Waiting for API readiness"
ready=0
for _ in $(seq 1 30); do
  if curl -fsS "${SMOKE_BASE_URL}/api/ready" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [[ "${ready}" -ne 1 ]]; then
  echo "error: API did not become ready" >&2
  exit 1
fi
curl -fsS "${SMOKE_BASE_URL}/api/health"
curl -fsS "${SMOKE_BASE_URL}/api/ready"

echo "==> Mandatory post-deploy smoke gate"
SMOKE_CHECK_BASE_URL="${SMOKE_BASE_URL}" bash "${ROOT}/scripts/post-deploy-smoke.sh"

echo "Deploy completed successfully at $(git rev-parse --short HEAD)"
