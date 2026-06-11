# Architecture

TicketMaster je maly Docker Compose system slozeny z frontendu, backendu, PostgreSQL databaze a vyvojove SMTP sluzby.

## Komponenty

```text
browser
  -> frontend:80
       -> /api/* proxy -> api:8000
api:8000
  -> PostgreSQL db:5432
  -> SMTP mailpit:1025 nebo produkcni SMTP
  -> GitLab API jen pri realne konfiguraci
```

## Backend

Backend je FastAPI aplikace. Business pravidla jsou vynucena v servisni vrstve:

- `services/tickets.py` - ticket druhy, viditelnost, workflow, komentare, participanty, resolver team, assignee.
- `services/admin.py` - partneri, klienti, uzivatele, odpovedne osoby, ochrana posledniho Admina.
- `services/gitlab.py` - GitLab issue pro L3.
- `services/notifications.py` - evidence a odeslani e-mailu.
- `services/audit.py` - audit log.

## Frontend

Frontend je React modul v TeskaLabs ASAB WebUI shellu. Frontend pouze zobrazuje dostupne akce a zlepsuje UX; oprávneni a workflow se vynucuji na backendu.

## Data

PostgreSQL uchovava:

- partnery, klienty a uzivatele,
- tickety vcetne `system` priznaku,
- participanty a watchery,
- komentare a interni poznamky,
- prilohy,
- GitLab vazby,
- notifikace,
- audit log.

Tickety, komentare a interni poznamky se nikdy nemazou.

## Zjednoduseny stack

V MVP nejsou soucasti runtime:

- Elasticsearch,
- Redis queue,
- PgBouncer,
- ClamAV container,
- Prometheus/Grafana/Loki/Promtail,
- samostatny worker.

Fulltext pouziva databazove/SQL vyhledavani v aplikaci. Notifikace se eviduji v databazi a odesilaji synchronne pri explicitnim testu nebo dalsim zpracovani v aplikaci.
