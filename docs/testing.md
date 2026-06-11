# Testing

## Backend testy

Lokálně:

```bash
cd backend
python3 -m pytest -q
```

V Dockeru:

```bash
docker compose build api
docker compose run --rm api python -m pytest -q
```

## Frontend build

```bash
cd frontend
npm install
npm run build
```

Nebo pres Docker:

```bash
docker compose build frontend
```

## Compose kontrola

```bash
docker compose config
docker compose up -d --build
curl -fsS http://127.0.0.1:3006/api/ready
```

## Co testy pokryvaji

- aktivni/neaktivni ucty,
- izolaci partneru,
- partner a klient administraci,
- odpovedne osoby klientu,
- partner, internal a system tickety,
- workflow a dostupne prechody,
- uzavrene tickety,
- resolver team a assignee,
- participanty,
- komentare a interni poznamky,
- zakaz editace a mazani komentaru,
- GitLab guard pro L3,
- audit a notifikace,
- ochranu posledniho aktivniho Admina.
