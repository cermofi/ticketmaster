# TicketMaster MVP

TicketMaster is a Dockerized MVP ticketing system for partner communication, internal resolver queues, e-mail notifications, GitLab-backed L3 work, audit logging, and an application CLI.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

On this Mac the legacy Compose binary is installed, so the equivalent verified command is:

```bash
docker-compose up --build
```

Open:

- WebUI and proxied API: http://localhost:3006
- API docs through nginx: http://localhost:3006/api/docs
- Mailpit: internal Docker service `mailpit:8025`

Seed development data:

```bash
docker compose exec api ticketmaster-cli db migrate
docker compose exec api ticketmaster-cli db seed-dev
```

Legacy local equivalent:

```bash
docker-compose exec api ticketmaster-cli db migrate
docker-compose exec api ticketmaster-cli db seed-dev
```

Default seeded users:

- `admin@example.test`, internal dev SSO
- `dm@example.test`, internal dev SSO
- `l1@example.test`, `l2@example.test`, `l3@example.test`, internal dev SSO
- `responsible@acme.example`, partner password from `TICKETMASTER_DEV_PASSWORD`
- `technical@acme.example`, partner password from `TICKETMASTER_DEV_PASSWORD`

## Stack

- Backend: FastAPI, SQLAlchemy, PostgreSQL.
- Frontend: React, ASAB WebUI shell/components, Reactstrap, Bootstrap.
- Mail: Mailpit in development, SMTP configurable.
- GitLab: dry-run by default, real GitLab API when configured.
- CLI: `ticketmaster-cli` inside the `api` container.

## Documentation

MkDocs site:

```bash
python -m pip install -r docs/requirements.txt
mkdocs serve
```

- [Architecture](docs/architecture.md)
- [UI Guide](docs/ui.md)
- [Development](docs/development.md)
- [Deployment](docs/deployment.md)
- [Configuration](docs/configuration.md)
- [CLI](docs/cli.md)
- [API](docs/api.md)
- [RBAC](docs/rbac.md)
- [GitLab integration](docs/gitlab-integration.md)
- [Testing](docs/testing.md)
