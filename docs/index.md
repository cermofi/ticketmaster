# TicketMaster

TicketMaster je jednoducha MVP aplikace pro evidenci a reseni ticketu mezi partnery, internim tymem a systemovymi integracemi.

Aktualni zdroj pravdy pro business logiku je dokument [TicketMaster - aplikacni logika](ticketmaster_aplikacni_logika.md).

## Runtime sluzby

| Sluzba | Interni adresa | Exponovana adresa |
| --- | --- | --- |
| Frontend + dokumentace | `frontend:80` | `127.0.0.1:3006` |
| API | `api:8000` | pres frontend `/api` |
| PostgreSQL | `db:5432` | nepublikovano |
| Mailpit SMTP | `mailpit:1025` | nepublikovano |

Databaze neni vystavena mimo Docker sit. Verejny vstup je jen frontend na `127.0.0.1:3006`; na VPS pred nim muze byt nginx reverse proxy.

## Rychly start

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T api ticketmaster-cli db seed-dev
curl -fsS http://127.0.0.1:3006/api/ready
```

## Struktura projektu

- `backend/ticketmaster/api` - FastAPI HTTP rozhrani.
- `backend/ticketmaster/services` - business logika.
- `backend/ticketmaster/models` - SQLAlchemy modely.
- `backend/migrations` - SQL migrace.
- `frontend/src/ticketmaster` - ASAB WebUI React modul.
- `docs` - MkDocs dokumentace.
- `docker-compose.yml` - jednoduchy runtime stack.

## Doporučene cteni

1. [Aplikacni logika](ticketmaster_aplikacni_logika.md)
2. [Architecture](architecture.md)
3. [API Reference](api.md)
4. [Docker & Deployment](deployment.md)
5. [Operations](operations.md)
6. [Testing](testing.md)
