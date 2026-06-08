# Docker & Deployment

Projekt je nasazeny jako jeden Docker Compose stack. Compose obsahuje aplikacni sluzby, databazi, queue, search, antivirus, monitoring a logovani.

## Prerekvizity hosta

- Linux VPS s Dockerem a Docker Compose pluginem.
- Dostatek RAM pro Elasticsearch, PostgreSQL a Grafanu.
- Nastaveny `vm.max_map_count=262144` pro Elasticsearch.

Nastaveni hosta:

```bash
cat >/etc/sysctl.d/99-ticketmaster-elasticsearch.conf <<'EOF'
vm.max_map_count=262144
EOF
sysctl -w vm.max_map_count=262144
```

## Struktura deploymentu

```text
/home/ticketmaster
  backend/
  frontend/
  docs/
  grafana/
  loki/
  pgbouncer/
  prometheus/
  promtail/
  docker-compose.yml
  mkdocs.yml
  .env
```

## Spusteni

```bash
cd /home/ticketmaster
docker compose up -d
docker compose ps
```

## Build po zmene kodu

Backend:

```bash
docker compose build api worker
docker compose up -d --force-recreate api worker
```

Frontend a dokumentace:

```bash
docker compose build frontend
docker compose up -d --force-recreate frontend
```

Cely stack:

```bash
docker compose build
docker compose up -d
```

## Migrace

Migrace jsou SQL soubory v `backend/migrations`. Worker pri startu spousti:

```bash
ticketmaster-cli db migrate
```

Manualni spusteni:

```bash
docker compose exec -T api ticketmaster-cli db migrate
```

## Seed dev dat

```bash
docker compose exec -T api ticketmaster-cli db seed-dev
```

Seed vytvari interni uzivatele, partnera, klienta, partner responsible/technical uzivatele a testovaci ticket.

## Health checks

```bash
curl -fsS http://127.0.0.1:3006/api/ready
curl -fsS http://127.0.0.1:9091/-/ready
curl -fsS http://127.0.0.1:9200/_cluster/health?pretty
curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:3007/login
```

## Reverse proxy pred aplikaci

Compose binduje porty na localhost. Produkcni verejny vstup by mel byt pres reverzni proxy na hostu, napr. nginx nebo Traefik.

Minimalni smerovani:

```text
https://ticketmaster.example.com -> 127.0.0.1:3006
```

Doporuceni:

- TLS terminace na host proxy.
- Forwardovani `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Request-ID`.
- Nastavit `APP_BASE_URL` na verejnou HTTPS adresu.
- Nastavit konkretni `TRUSTED_HOSTS`.
- Nastavit konkretni `CORS_ORIGINS`.

## Persistentni volumes

| Volume | Obsah |
| --- | --- |
| `postgres_data` | PostgreSQL data |
| `uploads` | ulozene prilohy |
| `redis_data` | Redis appendonly data |
| `elasticsearch_data` | Elasticsearch index |
| `clamav_data` | ClamAV signatures |
| `prometheus_data` | Prometheus TSDB |
| `grafana_data` | Grafana data |
| `loki_data` | Loki log storage |

## Backup

### PostgreSQL

```bash
docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

### Uploady

```bash
docker run --rm -v ticketmaster_uploads:/data -v "$PWD":/backup alpine \
  tar czf /backup/uploads.tar.gz -C /data .
```

### Grafana

Grafana datasource provisioning je v repozitari. Persistovana runtime data jsou ve volume `grafana_data`.

## Restore

1. Zastavit API/worker.
2. Obnovit PostgreSQL dump.
3. Obnovit upload volume.
4. Spustit migrace.
5. Reindexovat Elasticsearch.
6. Spustit API/worker/frontend.

```bash
docker compose stop api worker
docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup.sql
docker compose exec -T api ticketmaster-cli db migrate
docker compose exec -T api ticketmaster-cli search reindex-tickets
docker compose up -d
```

## Reindex Elasticsearch

```bash
docker compose exec -T api ticketmaster-cli search reindex-tickets
curl -fsS -X POST http://127.0.0.1:9200/ticketmaster-tickets/_refresh
curl -fsS http://127.0.0.1:9200/ticketmaster-tickets/_count?pretty
```

## Upgrade postup

1. Zkontrolovat `.env` a kompatibilitu compose.
2. Spustit testy v nove image.
3. Rebuildnout zmenene image.
4. Nasadit API/worker.
5. Nasadit frontend.
6. Overit health checks.
7. Zkontrolovat Grafanu a logy.

```bash
docker compose build api worker frontend
docker run --rm ticketmaster-api python -m pytest tests/test_business_rules.py -q
docker compose up -d --force-recreate api worker frontend
docker compose ps
```

