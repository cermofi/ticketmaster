# Operations

## Stav stacku

```bash
cd /home/new-ticketmaster
docker compose ps
```

Kriticke sluzby jsou `db`, `api` a `frontend`. `mailpit` je vyvojove SMTP.

## Logy

```bash
docker compose logs --tail=100 api
docker compose logs --tail=100 frontend
docker compose logs --tail=100 db
docker compose logs --tail=100 mailpit
```

## Health checks

```bash
curl -fsS http://127.0.0.1:3006/api/health
curl -fsS http://127.0.0.1:3006/api/ready
```

## Admin a seed

Vytvoreni prvniho Admina pres CLI:

```bash
docker compose exec -T api ticketmaster-cli user create-internal \
  --email admin@example.com \
  --name "Admin" \
  --role Admin
```

Seed dev dat:

```bash
docker compose exec -T api ticketmaster-cli db seed-dev
```

## SMTP test

```bash
docker compose exec -T api ticketmaster-cli email test --to user@example.com
```

## Databaze

Pocet ticketu podle statusu:

```bash
docker compose exec -T db psql -U ticketmaster -d ticketmaster \
  -c "select status, count(*) from tickets group by status order by status;"
```

Migrace:

```bash
docker compose exec -T db psql -U ticketmaster -d ticketmaster \
  -c "select * from schema_migrations order by version;"
```

## Incidenty

### API neni ready

```bash
docker compose logs --tail=100 api
docker compose ps db api frontend
```

Typicke priciny:

- databaze jeste neni healthy,
- migrace selhala,
- chybi nebo je spatne nastavena promenna v `.env`.

### Login vraci Too many login attempts

Rate limit je v pameti API procesu. Restart API ho vynuluje:

```bash
docker compose restart api
```

### Upload nejde nahrat

Zkontrolujte:

- pripona je jedna z `.png`, `.jpg`, `.jpeg`, `.pdf`, `.txt`, `.log`, `.zip`,
- velikost je do 25 MB,
- volume `uploads` je dostupne.
