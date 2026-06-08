# Architecture

TicketMaster je rozdeleny na frontend, backend API, worker, databazi a provozni infrastrukturu. Cele runtime prostredi je popsane jednim `docker-compose.yml`.

## Komponenty

| Komponenta | Technologie | Odpovednost |
| --- | --- | --- |
| Frontend | React, Vite, Reactstrap, nginx | UI aplikace, proxy `/api`, staticke `/docs` |
| Backend API | FastAPI, SQLAlchemy | HTTP API, autentizace, business pravidla, metriky |
| Worker | Python CLI process | background job queue, retry notifikaci, search indexing |
| Database | PostgreSQL 16 | hlavni perzistence dat |
| Connection pool | pgBouncer | pooling databazovych spojeni |
| Queue/cache | Redis 7 | background queue a login rate-limit |
| Search | Elasticsearch 8 | fulltextovy index ticketu a komentaru |
| DB fulltext | PostgreSQL GIN indexes | fallback fulltext pres tickets/comments |
| Malware scan | ClamAV | kontrola uploadu pred ulozenim |
| Metrics | Prometheus | scrape API metrik |
| Dashboards | Grafana | vizualizace metrik, logu a Elasticsearch datasource |
| Logs | Loki + Promtail | sbirani Docker logu |
| Error telemetry | Sentry SDK | odesilani chyb pri nastavenem `SENTRY_DSN` |
| E-mail dev sink | Mailpit | SMTP endpoint pro test/dev e-maily |

## Vysokourovnova topologie

```text
Browser
  |
  v
frontend/nginx
  |-- static React app
  |-- /docs -> MkDocs static site
  '-- /api, /metrics -> api:8000

api:8000
  |-- SQLAlchemy -> pgbouncer:6432 -> db:5432
  |-- Redis -> redis:6379
  |-- Elasticsearch -> elasticsearch:9200
  |-- ClamAV -> clamav:3310
  |-- SMTP -> mailpit:1025 or production SMTP
  '-- Sentry SDK -> external Sentry DSN

worker
  |-- Redis BRPOP queue
  |-- SQLAlchemy -> pgbouncer
  |-- retry notifications
  '-- index tickets in Elasticsearch

prometheus -> api:/metrics
promtail -> Docker socket -> loki
grafana -> Prometheus + Loki + Elasticsearch
```

## Backend vrstvy

Backend je organizovany do nekolika vrstev:

- `api` - FastAPI routery, dependency injection, request/response handling.
- `services` - business pravidla a integrace.
- `models` - SQLAlchemy entity.
- `schemas` - serializace domenovych objektu na API odpovedi.
- `core` - konfigurace, databaze, security, telemetry.
- `cli` - provozni a administracni command line rozhrani.

## Datovy model

Hlavni tabulky:

| Tabulka | Ucel |
| --- | --- |
| `users` | interni a partner uzivatele |
| `partners` | partnerske organizace |
| `clients` | klienti patri partnerum |
| `client_assignments` | odpovedne osoby ke klientum |
| `tickets` | hlavni ticket data |
| `ticket_participants` | partner participanti v ticketu |
| `ticket_watchers` | prijemci notifikaci |
| `comments` | komunikace a interni poznamky |
| `comment_revisions` | historie editaci a mazani komentaru |
| `attachments` | metadata uploadu |
| `gitlab_links` | napojeni ticketu na GitLab issue |
| `gitlab_sync_events` | historie GitLab synchronizaci |
| `notifications` | e-mail notifikace a retry stav |
| `audit_logs` | auditni stopa akci |

## Request lifecycle

1. Nginx ve frontend containeru prijme request.
2. Staticke soubory obslouzi primo; API requesty proxyuje na `api:8000`.
3. FastAPI middleware prida request ID, security headers, log zaznam a Prometheus metriku.
4. Router nacte aktualniho uzivatele z bearer tokenu.
5. Service vrstva provede business validaci, RBAC a databazove zmeny.
6. Zmeny se audituji do `audit_logs`.
7. Podle typu akce se zalozi notifikace nebo search indexing job.
8. Response se serializuje pres `schemas/serializers.py`.

## Background queue

Queue je implementovana pres Redis list.

- Producent: API nebo service vrstva vola enqueue.
- Transport: Redis list `ticketmaster:jobs`.
- Konzument: `ticketmaster-worker`.
- Polling: `BRPOP` s timeoutem.
- Chovani pri vypadku Redis: worker resetuje klienta a pokracuje po kratke pauze.

Podporovane joby:

| Job | Ucel |
| --- | --- |
| `notifications.retry_failed` | odeslani pending/failed notifikaci |
| `search.index_ticket` | reindex jednoho ticketu v Elasticsearch |
| `search.reindex_tickets` | reindex vsech ticketu |

## Vyhledavani

Vyhledavani pouziva vrstveny pristup:

1. Pokud je zapnuty Elasticsearch, API ziska matching ticket IDs z ES.
2. ID seznam se aplikuje jako predvyber, ale RBAC filtr zustava v databazi.
3. Pokud ES neni dostupny, PostgreSQL pouzije fulltext `to_tsvector` pres title/description/comments.
4. Pokud nejde PostgreSQL fulltext, pouzije se fallback `ILIKE`.

Tento model chrani opravneni: Elasticsearch nikdy sam nerozhoduje, co uzivatel smi videt.

## Uploady

Upload flow:

1. API zkontroluje opravneni komentovat ticket.
2. Overi povolenou priponu.
3. Overi velikost do 25 MB.
4. Odesle obsah do ClamAV pres `INSTREAM`.
5. Pokud je soubor cisty, ulozi ho do Docker volume `uploads`.
6. Zapise metadata do `attachments`.

## Observabilita

API publikuje `/metrics` s:

- `ticketmaster_http_requests_total`
- `ticketmaster_http_request_duration_seconds`
- standardnimi Python/process metrikami z `prometheus-client`

Prometheus scrapeuje API, Grafana ma datasource pro Prometheus, Loki a Elasticsearch. Promtail cte Docker event/log metadata pres Docker socket a posila logy do Loki.

