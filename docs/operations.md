# Operations & Monitoring

Tato stranka obsahuje provozni postupy pro bezny beh, diagnostiku a monitoring.

## Stav stacku

```bash
cd /home/ticketmaster
docker compose ps
```

Zdrave sluzby maji byt `Up` a u kritickych komponent `healthy`:

- `api`
- `frontend`
- `db`
- `pgbouncer`
- `redis`
- `elasticsearch`
- `clamav`

## Logy

### Docker Compose logy

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
docker compose logs --tail=100 frontend
```

### Loki/Grafana

Promtail sbira logy Docker containeru a posila je do Loki. V Grafane je Loki datasource predkonfigurovany.

Typicke dotazy:

```text
{container=~".*ticketmaster-api.*"}
{container=~".*ticketmaster-worker.*"}
{container=~".*ticketmaster-frontend.*"}
```

## Metriky

API publikuje Prometheus metriky na `/metrics`.

Kontrola:

```bash
curl -fsS http://127.0.0.1:3006/metrics | head
curl -fsS http://127.0.0.1:9091/-/ready
```

Dulezite metriky:

| Metrika | Popis |
| --- | --- |
| `ticketmaster_http_requests_total` | pocet HTTP requestu podle method/path/status |
| `ticketmaster_http_request_duration_seconds` | latence HTTP requestu |
| `process_*` | standardni procesni metriky |
| `python_gc_*` | Python GC metriky |

## Grafana

Grafana je dostupna na:

```text
http://127.0.0.1:3007/login
```

Datasource jsou provisionovane:

- Prometheus,
- Loki,
- Elasticsearch.

## Redis queue

Kontrola Redis:

```bash
docker compose exec -T redis redis-cli ping
docker compose exec -T redis redis-cli llen ticketmaster:jobs
```

Pokud queue roste:

1. zkontrolovat worker logy,
2. zkontrolovat Redis dostupnost,
3. zkontrolovat SMTP/Elasticsearch chyby podle typu jobu.

```bash
docker compose logs --tail=100 worker
```

## Notifikace

Manualni retry:

```bash
docker compose exec -T api ticketmaster-cli notifications retry-failed
```

SMTP test:

```bash
docker compose exec -T api ticketmaster-cli email test --to user@example.com
```

## Elasticsearch

Health:

```bash
curl -fsS http://127.0.0.1:9200/_cluster/health?pretty
```

Pocet dokumentu:

```bash
curl -fsS http://127.0.0.1:9200/ticketmaster-tickets/_count?pretty
```

Reindex:

```bash
docker compose exec -T api ticketmaster-cli search reindex-tickets
curl -fsS -X POST http://127.0.0.1:9200/ticketmaster-tickets/_refresh
```

## PostgreSQL

Pocet ticketu:

```bash
docker compose exec -T db psql -U ticketmaster -d ticketmaster \
  -c "select status, count(*) from tickets group by status order by status;"
```

Kontrola migraci:

```bash
docker compose exec -T db psql -U ticketmaster -d ticketmaster \
  -c "select * from schema_migrations order by version;"
```

Kontrola fulltext indexu:

```bash
docker compose exec -T db psql -U ticketmaster -d ticketmaster \
  -c "select indexname from pg_indexes where schemaname = 'public' and indexname like 'idx_%fulltext%';"
```

## ClamAV

ClamAV health:

```bash
docker compose ps clamav
docker compose logs --tail=50 clamav
```

Pokud uploady padaji na scan timeoutu:

1. zkontrolovat, ze `clamav` container je healthy,
2. zkontrolovat aktualizaci signatur,
3. zvysit `CLAMAV_TIMEOUT_SECONDS`,
4. zkontrolovat velikost souboru a dostupnou RAM.

## pgBouncer

Kontrola:

```bash
docker compose ps pgbouncer
```

Pokud API hlasi DB connection chyby:

1. zkontrolovat `db` health,
2. zkontrolovat `pgbouncer` health,
3. zkontrolovat `PGBOUNCER_DEFAULT_POOL_SIZE`,
4. zkontrolovat pocet API workeru (`WEB_CONCURRENCY`).

## Incident runbook

### API neni ready

```bash
docker compose logs --tail=100 api
docker compose ps db pgbouncer redis elasticsearch clamav
curl -fsS http://127.0.0.1:3006/api/ready
```

Typicke priciny:

- DB neni dostupna,
- pgBouncer neprosel healthcheckem,
- ClamAV dlouho startuje,
- Elasticsearch nema host sysctl `vm.max_map_count`.

### Login vraci Too many login attempts

Redis klíče:

```bash
docker compose exec -T redis redis-cli --scan --pattern 'ticketmaster:login-rate:*'
```

Po uspesnem loginu se aktualni klic maze. Pokud je potreba nouzove odblokovani:

```bash
docker compose exec -T redis redis-cli --scan --pattern 'ticketmaster:login-rate:*' \
  | xargs -r docker compose exec -T redis redis-cli del
docker compose restart api
```

### Search nevraci ocekavane vysledky

1. zkontrolovat ES health,
2. provest reindex,
3. zkontrolovat DB fallback fulltext indexy,
4. overit RBAC - ticket muze existovat, ale uzivatel ho nemusi smet videt.

