#!/usr/bin/env bash
# Production deploy: pull → migrate → build → smoke, with rollback marker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

ROLLBACK_DIR="${ROOT}/.deploy"
ROLLBACK_FILE="${ROLLBACK_DIR}/last-good-rev"
SMOKE_BASE_URL="${SMOKE_CHECK_BASE_URL:-https://ticketmaster.cermofi.cz}"
COMPOSE=(docker compose -f "${ROOT}/docker-compose.yml")

mkdir -p "${ROLLBACK_DIR}"

on_fail() {
  echo ""
  echo "=== DEPLOY FAILED — rollback instructions ==="
  echo "  cd ${ROOT}"
  echo "  git checkout ${PRE_DEPLOY_REV}"
  echo "  docker compose up -d --build"
  echo "  docker compose exec -T api ticketmaster-cli db migrate"
  echo "  curl -fsS ${SMOKE_BASE_URL}/api/ready"
  echo "============================================="
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
echo "To rollback: git checkout ${PRE_DEPLOY_REV} && ${COMPOSE[*]} up -d --build && ${COMPOSE[*]} exec -T api ticketmaster-cli db migrate"

echo "==> Pulling latest main (ff-only)"
git pull --ff-only origin main

echo "==> Running database migrations"
"${COMPOSE[@]}" exec -T api ticketmaster-cli db migrate

echo "==> Building and restarting changed services"
HEAD_REV="$(git rev-parse HEAD)"
if [ "$PRE_DEPLOY_REV" != "$HEAD_REV" ] || git diff --name-only "${PRE_DEPLOY_REV}" HEAD | grep -qE '^(backend/|frontend/|docs-site/|docker-compose)'; then
  "${COMPOSE[@]}" up -d --build
else
  echo "No service image changes detected; restarting api and frontend only"
  "${COMPOSE[@]}" up -d api frontend
fi

echo "==> Waiting for API readiness"
for _ in $(seq 1 30); do
  if curl -fsS "${SMOKE_BASE_URL}/api/ready" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
curl -fsS "${SMOKE_BASE_URL}/api/ready"

echo "==> Post-deploy smoke check"
SMOKE_CHECK_BASE_URL="${SMOKE_BASE_URL}" bash "${ROOT}/scripts/post-deploy-smoke.sh"

echo "Deploy completed successfully at $(git rev-parse --short HEAD)"
