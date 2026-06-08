# CLI

Backend image instaluje command line entrypoint:

```bash
ticketmaster-cli
```

CLI je urcene pro migrace, seed, administraci, GitLab operace, notifikace a search reindex. V Docker stacku se spousti typicky pres API container.

```bash
cd /home/ticketmaster
docker compose exec -T api ticketmaster-cli <command>
```

## Health

```bash
ticketmaster-cli health
```

Overi DB spojeni a vrati JSON status.

## Konfigurace

```bash
ticketmaster-cli config check
```

Vraci zakladni runtime konfiguraci, SMTP nastaveni, GitLab konfiguraci a upload dir.

## Databaze

```bash
ticketmaster-cli db migrate
ticketmaster-cli db seed-dev
```

`db migrate` aplikuje SQL migrace. `db seed-dev` vytvori vyvojova data.

## Uzivatele

```bash
ticketmaster-cli user create-internal --email admin@example.test --name "Admin User" --role Admin
ticketmaster-cli user deactivate --email old@example.test
ticketmaster-cli user list
```

Role pro internal user:

- `Admin`
- `DeliveryManager`
- `L1`
- `L2`
- `L3`

## Partneri

```bash
ticketmaster-cli partner create --name "Acme Partner"
ticketmaster-cli partner list
```

## Klienti

```bash
ticketmaster-cli client create --partner acme-partner --name "Acme Bank"
ticketmaster-cli client list --partner acme-partner
ticketmaster-cli client assign-responsible --client acme-partner-acme-bank --user responsible@acme.example
```

## Partner uzivatele

```bash
ticketmaster-cli partner-user invite \
  --partner acme-partner \
  --email responsible@acme.example \
  --name "Responsible User" \
  --role responsible
```

Role:

- `responsible`
- `technical`

Deaktivace:

```bash
ticketmaster-cli partner-user deactivate --email responsible@acme.example
```

## Tickety

```bash
ticketmaster-cli ticket show --id <ticket-id>
ticketmaster-cli ticket assign --id <ticket-id> --team L2 --assignee l2@example.test
ticketmaster-cli ticket transfer-owner --id <ticket-id> --new-owner new-owner@example.test
ticketmaster-cli ticket close --id <ticket-id>
```

Internal ticket:

```bash
ticketmaster-cli ticket create-internal \
  --type "Operational Request" \
  --priority Normal \
  --title "Internal task" \
  --description "Details" \
  --team L1
```

## GitLab

```bash
ticketmaster-cli gitlab check
ticketmaster-cli gitlab create-issue --ticket <ticket-id>
ticketmaster-cli gitlab sync-status --ticket <ticket-id>
```

## E-mail a notifikace

```bash
ticketmaster-cli email test --to user@example.com
ticketmaster-cli notifications retry-failed
```

## Search

```bash
ticketmaster-cli search reindex-tickets
```

Reindexuje vsechny tickety do Elasticsearch indexu.

## CLI actor

CLI operace pouzivaji systemoveho uzivatele:

```text
cli-system@ticketmaster.local
```

Pokud neexistuje, CLI ho vytvori jako internal `Admin`.

