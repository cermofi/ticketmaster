#!/usr/bin/env bash
# Generate and apply strong APP_SECRET + TICKETMASTER_DEV_PASSWORD in production .env.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "error: ${ENV_FILE} not found" >&2
  exit 1
fi

generate_secret() {
  python3 - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
print("".join(secrets.choice(alphabet) for _ in range(48)))
PY
}

APP_SECRET_NEW="$(generate_secret)"
DEV_PASSWORD_NEW="$(generate_secret)"

backup="${ENV_FILE}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
cp "${ENV_FILE}" "${backup}"

python3 - <<PY
from pathlib import Path

env_path = Path("${ENV_FILE}")
lines = env_path.read_text().splitlines()
updates = {
    "APP_SECRET": "${APP_SECRET_NEW}",
    "TICKETMASTER_DEV_PASSWORD": "${DEV_PASSWORD_NEW}",
}
seen = set()
out = []
for line in lines:
    if not line or line.lstrip().startswith("#") or "=" not in line:
        out.append(line)
        continue
    key, _ = line.split("=", 1)
    key = key.strip()
    if key in updates:
        out.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n")
PY

echo "Rotated APP_SECRET and TICKETMASTER_DEV_PASSWORD in ${ENV_FILE}"
echo "Backup saved: ${backup}"
echo "Restart API after rotation: docker compose up -d --build api"
