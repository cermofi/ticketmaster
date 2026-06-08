# GitLab Integration

GitLab integrace slouzi hlavne pro L3 workflow. Ticket prirazeny na `L3` ma mit odpovidajici GitLab issue a prechod do `In progress` je chraneny guardem.

## Konfigurace

```env
GITLAB_BASE_URL=https://gitlab.example.com
GITLAB_PROJECT_ID=group/project
GITLAB_TOKEN=<private-token>
GITLAB_DRY_RUN=false
```

V developmentu je mozne pouzit:

```env
GITLAB_DRY_RUN=true
```

Dry-run nevytvari realne GitLab issue, ale ulozi fake `GitLabLink`.

## Kontrola konfigurace

API:

```http
GET /api/gitlab/check
```

CLI:

```bash
docker compose exec -T api ticketmaster-cli gitlab check
```

Response obsahuje:

- `configured`,
- `dry_run`,
- `base_url`,
- `project_id`.

## Zalozeni issue

Kdy se issue vytvari:

- pri assignu ticketu na `L3`,
- pri vytvoreni internal ticketu s `team=L3`,
- manualne tlacitkem `Create GitLab issue`,
- manualne CLI prikazem.

CLI:

```bash
docker compose exec -T api ticketmaster-cli gitlab create-issue --ticket <ticket-id>
```

API:

```http
POST /api/tickets/{ticket_id}/gitlab/create-issue
```

## Obsah GitLab issue

Issue title:

```text
[TicketMaster] <ticket title>
```

Issue description obsahuje:

- Ticket ID,
- Ticket URL,
- Ticket type,
- Priority,
- Resolver team,
- puvodni description.

## Synchronizace statusu

API:

```http
POST /api/tickets/{ticket_id}/gitlab/sync-status
```

CLI:

```bash
docker compose exec -T api ticketmaster-cli gitlab sync-status --ticket <ticket-id>
```

Mapovani:

| GitLab state/label | TicketMaster GitLab status |
| --- | --- |
| closed issue | `Closed` |
| label `To Do` | `To Do` |
| label `In Progress` | `In Progress` |
| label `Done` | `Done` |
| jinak opened | `Open` |

## L3 guard

Pokud je ticket `L3` a uzivatel se pokusi prejit na `In progress`, backend kontroluje, ze existuje hlavni GitLab link. Pokud neexistuje, vrati konflikt.

Smysl guardu:

- L3 prace ma byt trasovatelna ve vyvojovem nastroji,
- TicketMaster zustava koordinacni system,
- GitLab zustava misto pro technickou implementaci.

## Troubleshooting

### `GITLAB_PROJECT_ID is not configured`

Nastavit:

```env
GITLAB_PROJECT_ID=group/project
```

### `GITLAB_TOKEN is not configured`

Pokud `GITLAB_DRY_RUN=false`, musi byt nastaven token:

```env
GITLAB_TOKEN=<private-token>
```

### Issue se nevytvari pri assignu na L3

Assign zustane platny, ale guard zablokuje prechod do `In progress`, dokud issue nevznikne. Zkontrolovat:

```bash
docker compose logs --tail=100 api
docker compose exec -T api ticketmaster-cli gitlab check
```

### Status se nesynchronizuje

Zkontrolovat:

- ze ticket ma `gitlab_links` zaznam,
- ze token ma pristup k projektu,
- ze `GITLAB_BASE_URL` neobsahuje spatnou cestu,
- ze GitLab issue existuje.

