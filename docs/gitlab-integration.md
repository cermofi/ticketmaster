# GitLab Integration

GitLab integrace slouzi pro L3 praci.

## Konfigurace

```env
GITLAB_BASE_URL=https://gitlab.example.com
GITLAB_PROJECT_ID=group/project
GITLAB_TOKEN=<private-token>
GITLAB_DRY_RUN=false
```

V developmentu je vychozi `GITLAB_DRY_RUN=true`, kdy se vytvori pouze dry-run link.

## Kdy vznikne issue

GitLab issue musi vzniknout:

- pri vytvoreni ticketu rovnou pro `L3`,
- pri prirazeni existujiciho ticketu na `L3`.

Pokud se issue nepodari zalozit, ticket se nesmi vytvorit/priradit do `L3`.

## Viditelnost

- Interni uzivatel vidi GitLab URL.
- Partner vidi pouze GitLab status.

## CLI

```bash
docker compose exec -T api ticketmaster-cli gitlab check
docker compose exec -T api ticketmaster-cli gitlab create-issue --ticket <ticket-id>
docker compose exec -T api ticketmaster-cli gitlab sync-status --ticket <ticket-id>
```

## L3 guard

L3 ticket bez GitLab issue nemuze prejit do `In progress`.
