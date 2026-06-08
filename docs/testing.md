# Testing

Projekt obsahuje automatizovane backend testy a doporucene smoke testy pro produkcni Docker stack.

## Automatizovane testy

Spusteni v backend image:

```bash
docker run --rm ticketmaster-api python -m pytest tests/test_business_rules.py -q
```

Nebo po buildu:

```bash
docker compose build api worker
docker run --rm ticketmaster-api python -m pytest tests/test_business_rules.py -q
```

Aktualni hlavni sada overuje business pravidla:

- vytvareni partner ticketu,
- role partner `responsible`/`technical`,
- client assignment pravidla,
- workflow prechody,
- L3 GitLab guard,
- komentare a internal notes,
- participant management,
- owner visibility,
- deaktivacni guardy.

## CLI testy

```bash
docker run --rm ticketmaster-api python -m pytest tests/test_cli.py -q
```

## Smoke test po deployi

```bash
cd /home/ticketmaster
docker compose ps
curl -fsS http://127.0.0.1:3006/api/ready
curl -fsS http://127.0.0.1:3006/metrics | head
curl -fsSI http://127.0.0.1:3006/docs/ | head
curl -fsS http://127.0.0.1:9091/-/ready
curl -fsS http://127.0.0.1:9200/_cluster/health?pretty
curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:3007/login
```

## Manualni UI checklist

### Login

- partner responsible se prihlasi heslem,
- partner technical se prihlasi heslem,
- interni uzivatel projde dev SSO,
- opakovany uspesny login nezpusobi `Too many login attempts`.

### Dashboard

- filtry se aplikuji automaticky,
- reset filtru funguje,
- pagination ukazuje spravne rozsahy,
- L1/L2/L3 vidi vlastnene a prirazene tickety,
- partner vidi svoje partner tickety.

### Ticket detail

- detail nema horizontalni scroll na beznem monitoru,
- closed ticket nezobrazuje formular komentare,
- technical partner vidi participanty bez zmenovych tlacitek,
- owner muze pridat/odebrat participanta,
- owner nejde odebrat z participantu,
- internal note vidi jen interni uzivatel.

### Create ticket

- responsible partner muze vytvorit partner ticket,
- technical partner nema moznost vytvorit ticket,
- interni uzivatel muze vytvorit internal ticket,
- creator internal ticketu je owner a vidi ticket v dashboardu.

### Admin

- Admin vidi partner/client/user spravu,
- DeliveryManager nema admin-only akce,
- nelze deaktivovat posledniho Admina,
- nelze deaktivovat partnera s aktivnimi zavislostmi.

### Audit

- Admin/DeliveryManager vidi audit,
- ostatni role jsou odmítnute,
- login a login failure jsou zapsane s IP/user-agent informacemi.

## Search testy

```bash
docker compose exec -T api ticketmaster-cli search reindex-tickets
curl -fsS -X POST http://127.0.0.1:9200/ticketmaster-tickets/_refresh
curl -fsS http://127.0.0.1:9200/ticketmaster-tickets/_count?pretty
```

Manualne overit:

- hledani podle titulku,
- hledani podle popisu,
- hledani podle textu komentare,
- RBAC filtr - nalezeny ticket se nezobrazi neautorizovanemu uzivateli.

## Upload testy

- povoleny `.txt` upload projde,
- nepovolena pripona vrati chybu,
- soubor nad 25 MB vrati chybu,
- ClamAV container je healthy,
- download prilohy vyzaduje view opravneni k ticketu.

## Monitoring testy

- Prometheus scrapeuje API,
- Grafana vidi Prometheus datasource,
- Grafana vidi Loki datasource,
- Loki obsahuje logy API/worker/frontendu,
- Elasticsearch datasource je dostupny.

## Regression oblasti

Pri kazde vetsi zmene testovat hlavne:

- RBAC viditelnost ticketu,
- workflow prechody,
- closed ticket write guards,
- participant management,
- GitLab L3 guard,
- login rate-limit,
- upload scan,
- search fallback chovani.

