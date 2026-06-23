# Production runbook (TicketMaster)

Krátký provozní postup pro nasazení na VPS. Detailní dokumentace: https://ticketmaster.cermofi.cz/docs/provoz (jen interní síť) nebo `docs-site/content/docs/provoz.mdx` v repozitáři.

## Deploy

```bash
cd /home/new-ticketmaster
git pull origin main
docker compose up -d --build
docker compose exec api ticketmaster-cli db migrate
```

Po deployu ověřte health a spusťte smoke check.

## Health checks

| Endpoint | Účel |
| --- | --- |
| `GET /api/health` | Liveness — API běží |
| `GET /api/ready` | Readiness — DB dostupná |

```bash
curl -fsS https://ticketmaster.cermofi.cz/api/health
curl -fsS https://ticketmaster.cermofi.cz/api/ready
curl -fsS http://127.0.0.1:3006/docs/ | head
docker compose ps
docker compose logs --tail=100 api frontend docs
```

## Post-deploy smoke check (read-only)

Smoke check **nevytváří** produkční data a **nezapisuje audit** (hlavička `x-ticketmaster-smoke: 1`).

Defaultně volá jen veřejné GET endpointy (`/api/health`, `/api/ready`, `/api/meta`).

```bash
./scripts/post-deploy-smoke.sh
# nebo uvnitř API kontejneru:
docker compose exec api ticketmaster-cli smoke check
```

Volitelně (read-only autentizované kontroly):

```bash
SMOKE_ALLOW_AUTH=1 SMOKE_CHECK_EMAIL=... SMOKE_CHECK_PASSWORD=... ./scripts/post-deploy-smoke.sh
```

GitHub Actions: `.github/workflows/post-deploy-smoke.yml`.

## Rollback

```bash
cd /home/new-ticketmaster
git log --oneline -5
git checkout <predchozi-commit>
docker compose up -d --build
docker compose exec api ticketmaster-cli db migrate
curl -fsS https://ticketmaster.cermofi.cz/api/ready
```

Pokud nová migrace už proběhla, obnovte DB ze zálohy.

## DB backup / restore

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

Obnova (destruktivní):

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup-YYYY-MM-DD.sql
```

Volume: `postgres_data`. Viz `docs-site/content/docs/databaze.mdx`.

## Rate limit — konfigurace a reset

| Proměnná | Význam | Default |
| --- | --- | --- |
| `AUTH_RATE_LIMIT_ATTEMPTS` | Max pokusů ve window | `10` |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | Délka okna (s) | `300` |
| `LOGIN_RATE_LIMIT_*` | Alias | stejné |

Chráněné endpointy: `/api/auth/login`, `/api/auth/dev-sso`, `/api/auth/sign-in-as-partner`, `/api/auth/back-to-admin`.

```bash
docker compose exec api ticketmaster-cli rate-limit reset --scope login --ip <CLIENT_IP> --identifier user@example.com
docker compose exec api ticketmaster-cli rate-limit reset --scope sign-in-as-partner --ip <CLIENT_IP> --identifier <USER_ID>
docker compose exec api ticketmaster-cli rate-limit list
```

Pozn.: limit je in-memory na worker; při `WEB_CONCURRENCY>1` restartujte API.

## API chyby

```json
{
  "code": "permission_denied",
  "message": "Invalid e-mail or password",
  "details": null,
  "request_id": "uuid"
}
```

`X-Request-ID` v response odpovídá `request_id`.

## Incident triage

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose exec api ticketmaster-cli health
docker compose exec api ticketmaster-cli config check
docker compose exec api ticketmaster-cli gitlab check
docker compose exec api ticketmaster-cli notifications retry-failed
curl -fsS https://ticketmaster.cermofi.cz/api/ready
```

Více: `docs-site/content/docs/reseni-problemu.mdx`.
