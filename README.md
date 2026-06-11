# TicketMaster MVP

TicketMaster is a small Docker Compose ticketing application for partner support, internal resolver teams, system tickets, audit logging, notifications, attachments, and GitLab-backed L3 work.

The current product source of truth is `docs/ticketmaster_aplikacni_logika.md`.

## Quick Start

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec -T api ticketmaster-cli db seed-dev
```

Open:

- Web UI and proxied API: http://localhost:3006
- API docs: http://localhost:3006/api/docs
- MkDocs documentation: http://localhost:3006/docs/

Default seeded users:

- `admin@example.test`, internal dev SSO
- `dm@example.test`, internal dev SSO
- `l1@example.test`, `l2@example.test`, `l3@example.test`, internal dev SSO
- `responsible@acme.example`, partner password from `TICKETMASTER_DEV_PASSWORD`
- `technical@acme.example`, partner password from `TICKETMASTER_DEV_PASSWORD`

## Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL.
- Frontend: React with TeskaLabs ASAB WebUI shell/components, Reactstrap, Bootstrap.
- Database: PostgreSQL, private inside the Docker network.
- Mail: Mailpit by default, SMTP configurable.
- GitLab: dry-run by default, real GitLab API when configured.
- CLI: `ticketmaster-cli` inside the `api` container.

## Common Commands

```bash
docker compose ps
docker compose logs --tail=100 api
docker compose exec -T api ticketmaster-cli db migrate
docker compose exec -T api ticketmaster-cli db seed-dev
docker compose exec -T api python -m pytest -q
docker compose down
```

Persistent data is stored in Docker volumes `postgres_data`, `uploads`, and `api_logs`.
