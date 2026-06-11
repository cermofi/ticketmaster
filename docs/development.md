# Development

## Struktura

```text
backend/
  ticketmaster/
    api/
    cli/
    core/
    models/
    schemas/
    services/
  migrations/
  tests/
frontend/
  src/
    api/
    ticketmaster/
docs/
docker-compose.yml
```

## Backend vrstvy

- `api/routes.py` - HTTP endpointy.
- `api/deps.py` - DB session a current user.
- `services/tickets.py` - ticket workflow, visibility, komentare, assignment.
- `services/admin.py` - partneri, klienti, uzivatele.
- `services/auth.py` - login, dev SSO, aktivace.
- `services/notifications.py` - evidence a odeslani e-mailu.
- `services/gitlab.py` - GitLab issue/status.
- `models/entities.py` - SQLAlchemy modely.
- `schemas/serializers.py` - API vystup.

Business logika patri do service vrstvy. UI nikdy nesmi byt jedine misto, kde se hlida opravneni.

## Frontend

Frontend je React modul v ASAB WebUI:

- `TicketMasterModule.jsx` - routy a navigace.
- `DashboardScreen.jsx` - ticket list.
- `NewTicketScreen.jsx` - vytvoreni ticketu.
- `TicketDetailScreen.jsx` - detail ticketu.
- `AdminScreen.jsx` - administrace.
- `AuditScreen.jsx` - audit.
- `SettingsScreen.jsx` - lokalni UI preference.

## Databazove zmeny

1. Pridat SQL migraci do `backend/migrations`.
2. Pouzit idempotentni SQL, pokud to jde.
3. Aktualizovat SQLAlchemy model.
4. Pridat nebo upravit testy.
5. Spustit migrace a testy.

## Backend endpoint

1. Nejdriv service funkce s RBAC/business pravidly.
2. Audit pro zapisovou akci.
3. Route v `api/routes.py`.
4. Serializer pro odpoved.
5. Test v `backend/tests`.
6. Aktualizace `docs/api.md`.

## Dokumentace

MkDocs build je soucast frontend image:

```bash
docker compose build frontend
```

Lokální build:

```bash
pip install -r docs/requirements.txt
mkdocs build --site-dir /tmp/ticketmaster-docs
```
