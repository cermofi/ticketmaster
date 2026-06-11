# Docker & Deployment

Projekt se spousti jako jednoduchy Docker Compose stack.

## Sluzby

- `db` - PostgreSQL, pouze v interni Docker siti.
- `mailpit` - vyvojove SMTP prijimani.
- `api` - FastAPI backend, migrace se spusti pri startu containeru.
- `frontend` - ASAB WebUI build, MkDocs build a nginx proxy na `/api`.

## Spusteni

```bash
cd /home/new-ticketmaster
cp .env.example .env
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:3006/api/ready
```

## Zastaveni

```bash
docker compose down
```

## Migrace

```bash
docker compose exec -T api ticketmaster-cli db migrate
```

Migrace jsou SQL soubory v `backend/migrations` a jsou idempotentne evidovane v tabulce `schema_migrations`.

## Seed dev dat

```bash
docker compose exec -T api ticketmaster-cli db seed-dev
```

Seed vytvori interní role, partnera, klienta, odpovednou osobu, technickou osobu, partner ticket a system ticket.

## Persistentni data

| Volume | Obsah |
| --- | --- |
| `postgres_data` | PostgreSQL data |
| `uploads` | ulozene prilohy |
| `api_logs` | prostor pro aplikacni logy, pokud se budou zapisovat do souboru |

## Reverse proxy

Na VPS je ocekavany verejny vstup pres nginx proxy na:

```text
127.0.0.1:3006
```

Doporuceni:

- TLS ukoncit na host nginxu.
- Forwardovat `X-Forwarded-For`, `X-Forwarded-Proto` a `X-Request-ID`.
- Nastavit `APP_BASE_URL` na verejnou HTTPS adresu.
- V produkci nastavit konkretni `TRUSTED_HOSTS` a `CORS_ORIGINS`.

## Backup

PostgreSQL:

```bash
docker compose exec -T db pg_dump -U ticketmaster ticketmaster > backup.sql
```

Uploady:

```bash
docker run --rm -v new-ticketmaster_uploads:/data -v "$PWD":/backup alpine \
  tar czf /backup/uploads.tar.gz -C /data .
```
