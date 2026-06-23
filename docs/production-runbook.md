# Production runbook (TicketMaster)

Krátký provozní postup pro nasazení na VPS. Detailní dokumentace: https://ticketmaster.cermofi.cz/docs/provoz (jen interní síť) nebo `docs-site/content/docs/provoz.mdx` v repozitáři.

## Deploy

Preferovaný postup na VPS:

```bash
cd /home/new-ticketmaster
./scripts/deploy.sh
```

Skript automaticky:

0. v produkci (`TM_ENV=production`) ověří bezpečnou konfiguraci (`scripts/check-production-config.sh`) — selže při default `APP_SECRET`, `APP_DEBUG`, `ALLOW_SEED_DEV`, `ALLOW_DEV_SSO`, nebo default `TICKETMASTER_DEV_PASSWORD`
1. uloží rollback git revizi do `.deploy/last-good-rev`
2. zkontroluje pending migrace (`ticketmaster-cli db plan`)
3. u **risky** migrací vytvoří DB backup a rollback artifact (vyžaduje `MIGRATE_CONFIRM=1` v produkci)
4. spustí migrace, rebuild/restart služeb
5. **povinný** post-deploy smoke gate (`scripts/post-deploy-smoke.sh`) — při selhání deploy skončí s nenulovým exit kódem

Ruční kroky (ekvivalent skriptu):

```bash
cd /home/new-ticketmaster
git pull origin main
docker compose exec api ticketmaster-cli db plan
docker compose exec api ticketmaster-cli db migrate
docker compose up -d --build
./scripts/post-deploy-smoke.sh
```

## Risky migrations

Risky migrace = SQL obsahující `DROP TABLE`, `DROP COLUMN`, `ALTER COLUMN … TYPE`, `TRUNCATE`, nebo `DELETE FROM`.

| Krok | Chování |
| --- | --- |
| Detekce | `ticketmaster-cli db plan` vrátí `risky_pending` |
| Backup | `./scripts/db-backup-checkpoint.sh` → `.deploy/backups/pre-migrate-*.sql` |
| Potvrzení | V produkci `MIGRATE_CONFIRM=1` nebo `db migrate --confirm-risky` |
| Rollback artifact | `.deploy/rollback-*.md` s git rev, backup cestou a příkazy |
| Vypnutí backupu | `SKIP_MIGRATION_BACKUP=1` (jen pokud víte proč) |

Běžné index/create migrace nejsou risky a nevyžadují potvrzení.

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

## Post-deploy smoke gate (mandatory)

Smoke gate je **povinný** krok deploy pipeline. Selhání = deploy failed.

Smoke check **nevytváří** produkční data. Audit se u HTTP požadavků **vždy zapisuje**
(potlačení auditu je jen u interních CLI cest přes `suppress_audit()`).

Minimální sada (read-only):

- `GET /api/health`
- `GET /api/ready`
- `GET /api/meta`
- volitelně autentizované kontroly při `SMOKE_ALLOW_AUTH=1`

```bash
./scripts/post-deploy-smoke.sh
# nebo uvnitř API kontejneru:
docker compose exec api ticketmaster-cli smoke check
```

Volitelně (read-only autentizované kontroly):

```bash
SMOKE_ALLOW_AUTH=1 SMOKE_CHECK_EMAIL=... SMOKE_CHECK_PASSWORD=... ./scripts/post-deploy-smoke.sh
```

GitHub Actions: `.github/workflows/post-deploy-smoke.yml`, `.github/workflows/deploy.yml`.

## Rollback

```bash
cd /home/new-ticketmaster
git log --oneline -5
git checkout <predchozi-commit>
docker compose up -d --build
docker compose exec api ticketmaster-cli db migrate
curl -fsS https://ticketmaster.cermofi.cz/api/ready
./scripts/post-deploy-smoke.sh
```

Pokud nová **risky** migrace už proběhla, obnovte DB ze zálohy v `.deploy/backups/`.

## DB backup / restore

```bash
./scripts/db-backup-checkpoint.sh
# nebo ručně:
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup-$(date +%F).sql
```

Obnova (destruktivní):

```bash
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup-YYYY-MM-DD.sql
```

Volume: `postgres_data`. Viz `docs-site/content/docs/databaze.mdx`.

## Policy matrix

Autoritativní pravidla viditelnosti a klíčových akcí:
`backend/ticketmaster/policy/access_matrix.json`

Contract testy: `backend/tests/test_policy_contract.py`

## Rate limit — konfigurace a reset

| Proměnná | Význam | Default |
| --- | --- | --- |
| `AUTH_RATE_LIMIT_ATTEMPTS` | Max pokusů ve window | `10` |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | Délka okna (s) | `300` |
| `LOGIN_RATE_LIMIT_*` | Alias | stejné |

Chráněné endpointy: `/api/auth/login`, `/api/auth/dev-sso`, `/api/auth/activate`, `/api/auth/sign-in-as-partner`, `/api/auth/back-to-admin`.

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
