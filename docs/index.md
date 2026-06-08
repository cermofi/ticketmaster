# TicketMaster

TicketMaster je webova aplikace pro prijem, triazi, zpracovani a auditovani ticketu mezi partnerem a internimi resitelskymi tymy. Dokumentace popisuje aktualni stav projektu, API, uzivatelske role, Docker prostredi, provozni postupy a integrace.

Dokumentace je generovana frameworkem [MkDocs](https://github.com/mkdocs/mkdocs) a v produkcnim Docker stacku je publikovana pres frontend container na route `/docs`.

## Co aplikace resi

TicketMaster poskytuje jedno misto pro:

- vytvareni partner ticketu odpovednymi osobami partnera,
- vytvareni internich ticketu internimi rolemi,
- triazni dashboard s filtry, strankovanim a fulltextem,
- detail ticketu s komunikaci, internimi poznamkami, prilohami a workflow akcemi,
- spravu partneru, klientu, uzivatelu a odpovednych osob,
- auditni stopu dulezitych zmen,
- GitLab napojeni pro L3 praci,
- provozni observabilitu pres Prometheus, Grafanu, Loki, Promtail, Elasticsearch a Sentry SDK,
- malware kontrolu uploadu pres ClamAV.

## Hlavni adresy ve stacku

| Sluzba | Interni adresa | Exponovana adresa na VPS |
| --- | --- | --- |
| Frontend + dokumentace | `frontend:80` | `127.0.0.1:3006` |
| API | `api:8000` | pres frontend `/api` |
| MkDocs dokumentace | staticky build ve frontendu | `/docs/` |
| Prometheus | `prometheus:9090` | `127.0.0.1:9091` |
| Grafana | `grafana:3000` | `127.0.0.1:3007` |
| Elasticsearch | `elasticsearch:9200` | `127.0.0.1:9200` |
| PostgreSQL | `db:5432` | nepublikovano |
| pgBouncer | `pgbouncer:6432` | nepublikovano |
| Redis | `redis:6379` | nepublikovano |
| Loki | `loki:3100` | nepublikovano |
| ClamAV | `clamav:3310` | nepublikovano |

## Rychly provozni start

```bash
cd /home/ticketmaster
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:3006/api/ready
```

Ocekavana odpoved readiness endpointu:

```json
{"status":"ready","database":"ok"}
```

## Zdroj pravdy

Dokumentace popisuje kod v techto castech projektu:

- `backend/ticketmaster/api` - FastAPI routy a HTTP rozhrani.
- `backend/ticketmaster/services` - business logika ticketu, admin spravy, notifikaci, vyhledavani, GitLabu a job queue.
- `backend/ticketmaster/models` - SQLAlchemy modely a domenova data.
- `backend/migrations` - SQL migrace vcetne produkcnich indexu a PostgreSQL fulltextu.
- `frontend/src/ticketmaster` - React obrazovky aplikace.
- `docker-compose.yml` - kompletni runtime stack.
- `prometheus`, `grafana`, `loki`, `promtail`, `pgbouncer` - konfigurace provoznich komponent.

## Doporucony zpusob cteni

1. Pro business kontext zacnete strankou [Product Guide](product.md).
2. Pro technicky obraz celym systemem pokracujte na [Architecture](architecture.md).
3. Pro role a opravneni si prectete [RBAC & Workflow](rbac.md).
4. Pro nasazeni a provoz pouzijte [Docker & Deployment](deployment.md) a [Operations & Monitoring](operations.md).
5. Pro integrace a automatizaci pouzijte [API Reference](api.md), [CLI](cli.md) a [GitLab Integration](gitlab-integration.md).

