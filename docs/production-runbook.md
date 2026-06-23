# Production runbook (TicketMaster)

Krátký provozní postup pro nasazení na VPS. Detailnější dokumentace: `docs-site/content/docs/provoz.mdx`.

## Deploy

```bash
cd /home/new-ticketmaster
git pull origin main
docker compose up -d --build
docker compose exec api ticketmaster-cli db migrate
```

Po deployu ověřte health (viz níže) a spusťte smoke check.

## Health checks

| Endpoint | Účel |
| --- | --- |
| `GET /api/health` | Liveness — API běží |
| `GET /api/ready` | Readiness — DB dostupná |

```bash
curl -fsS https://ticketmaster.cermofi.cz/api/health
curl -fsS https://ticketmaster.cermofi.cz/api/ready
docker compose ps
docker compose logs --tail=100 api frontend
```

## Post-deploy smoke check (read-only)

Smoke check **nevytváří** produkční data. Defaultně volá jen veřejné GET endpointy (`/api/health`, `/api/ready`, `/api/meta`).

```bash
./scripts/post-deploy-smoke.sh
# nebo uvnitř API kontejneru:
docker compose exec api ticketmaster-cli smoke check
```

Volitelně (jen read-only autentizované kontroly, bez zápisu):

```bash
SMOKE_ALLOW_AUTH=1 SMOKE_CHECK_EMAIL=... SMOKE_CHECK_PASSWORD=... ./scripts/post-deploy-smoke.sh
```

GitHub Actions workflow: `.github/workflows/post-deploy-smoke.yml` (manual + po změně smoke skriptu).

## Rollback

```bash
cd /home/new-ticketmaster
git log --oneline -5
git checkout <predchozi-commit>
docker compose up -d --build
docker compose exec api ticketmaster-cli db migrate   # migrace jsou dopředné; rollback DB řešte zálohou
curl -fsS https://ticketmaster.cermofi.cz/api/ready
```

Pokud nová migrace už proběhla, obnovte DB ze zálohy (viz databáze).

## DB backup / restore

Záloha (příklad):

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

Obnova (⚠ destruktivní):

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup-YYYY-MM-DD.sql
```

Volume: `postgres_data`. Viz také `docs-site/content/docs/databaze.mdx`.

## Rate limit — konfigurace a reset

Proměnné prostředí (viz `.env`):

| Proměnná | Význam | Default |
| --- | --- | --- |
| `AUTH_RATE_LIMIT_ATTEMPTS` | Max pokusů ve window | `10` |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | Délka okna (s) | `300` |
| `LOGIN_RATE_LIMIT_*` | Alias pro zpětnou kompatibilitu | stejné |

Chráněné endpointy: `/api/auth/login`, `/api/auth/dev-sso`, `/api/auth/sign-in-as-partner`, `/api/auth/back-to-admin`.

**Reset po false positive** (uvnitř API kontejneru):

```bash
# login — identifier = e-mail
docker compose exec api ticketmaster-cli rate-limit reset --scope login --ip <CLIENT_IP> --identifier user@example.com

# sign-in-as-partner / back-to-admin — identifier = user id
docker compose exec api ticketmaster-cli rate-limit reset --scope sign-in-as-partner --ip <CLIENT_IP> --identifier <USER_ID>

# náhled aktivních klíčů
docker compose exec api ticketmaster-cli rate-limit list
```

Pozn.: limit je in-memory na worker; při `WEB_CONCURRENCY>1` resetujte nebo restartujte API (`docker compose restart api`).

## API chyby

Unified JSON tvar:

```json
{
  "code": "permission_denied",
  "message": "Invalid e-mail or password",
  "details": null,
  "request_id": "uuid"
}
```

`X-Request-ID` v response odpovídá `request_id` (nebo přebírá incoming header).

## Incident triage — rychlé příkazy

```bash
docker compose ps
docker compose logs --tail=200 api
docker compose logs --tail=100 frontend
docker compose exec api ticketmaster-cli health
docker compose exec api ticketmaster-cli config check
docker compose exec api ticketmaster-cli notifications retry-failed
curl -fsS https://ticketmaster.cermofi.cz/api/ready
```

Při podezření na blokovaný login: `rate-limit list` → `rate-limit reset` (viz výše).
