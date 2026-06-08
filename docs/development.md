# Development

Tato stranka popisuje, jak se v projektu orientovat a jak bezpecne rozsirovat aplikaci.

## Projektova struktura

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
mkdocs.yml
```

## Backend

Backend je Python aplikace s FastAPI a SQLAlchemy.

Vrstvy:

- `api/routes.py` - HTTP endpointy.
- `api/deps.py` - DB session a current user dependency.
- `services/tickets.py` - ticket workflow a RBAC.
- `services/admin.py` - partner/client/user management.
- `services/auth.py` - login, dev SSO, activation.
- `services/notifications.py` - notification queue a SMTP retry.
- `services/search.py` - Elasticsearch index a search.
- `services/malware.py` - ClamAV scan.
- `services/jobs.py` - Redis worker loop.
- `models/entities.py` - SQLAlchemy modely.
- `schemas/serializers.py` - API serializace.

## Frontend

Frontend je React aplikace.

Klicove soubory:

- `TicketMasterModule.jsx` - routy a navigace.
- `DashboardScreen.jsx` - dashboard, filtry, pagination, ticket forms.
- `NewTicketScreen.jsx` - vytvoreni ticketu.
- `TicketDetailScreen.jsx` - detail ticketu.
- `AdminScreen.jsx` - admin sprava.
- `AuditScreen.jsx` - audit.
- `SettingsScreen.jsx` - lokalni UI preference.
- `api/client.js` - axios klient a session helpers.

## Dokumentace

Dokumentace je MkDocs site:

- konfigurace `mkdocs.yml`,
- obsah v `docs/`,
- build bezi ve `frontend/Dockerfile`,
- vysledek se kopiruje do `/usr/share/nginx/html/docs`.

Lokální build dokumentace:

```bash
pip install -r docs/requirements.txt
mkdocs build --site-dir /tmp/ticketmaster-docs
```

V Docker stacku:

```bash
docker compose build frontend
docker compose up -d --force-recreate frontend
```

## Pridani backend endpointu

Doporuceny postup:

1. Pridat nebo upravit service funkci.
2. V service vrstve vynutit RBAC a business pravidla.
3. Pridat audit zaznam pro zapisovou akci.
4. Pokud akce meni ticket nebo komentare, enqueue search indexing.
5. Pridat route v `api/routes.py`.
6. Serializovat odpoved pres serializer.
7. Pridat test do `backend/tests`.
8. Aktualizovat dokumentaci v `docs/api.md`.

## Pridani databazove zmeny

1. Pridat SQL migraci do `backend/migrations`.
2. Pouzit idempotentni SQL, pokud je to mozne (`IF NOT EXISTS`).
3. Overit, ze migrace jde spustit opakovane bez zmeny dat.
4. Spustit:

```bash
docker compose exec -T api ticketmaster-cli db migrate
```

## Pridani UI obrazovky

1. Vytvorit komponentu ve `frontend/src/ticketmaster/screens`.
2. Pridat route do `TicketMasterModule.jsx`.
3. Pridat navigacni polozku jen pokud ma byt soucast hlavni navigace.
4. Pouzit `AuthGate`.
5. Osetrit loading/error stavy.
6. Schovat nepovolene akce podle role, ale nespolihat na UI jako security boundary.
7. Aktualizovat `docs/ui.md`.

## Pridani jobu

1. Pridat enqueue misto ve service vrstve.
2. Pridat handler v `services/jobs.py`.
3. Job musi byt idempotentni nebo bezpecny pri opakovani.
4. Logovat selhani.
5. Pokud job zapisuje do DB, pouzit session ve workeru.

## Kodove principy

- Business pravidla patri do service vrstvy, ne do UI.
- API routy maji byt tenke.
- Kazda zapisova akce ma audit.
- Dlouhe nebo opakovatelne akce patri do workeru.
- Search index je sekundarni; DB a RBAC jsou zdroj pravdy.
- UI muze schovat akce, ale API je musi vynutit.

