# CLI

Backend image obsahuje prikaz:

```bash
ticketmaster-cli
```

V Dockeru se spousti pres API container:

```bash
docker compose exec -T api ticketmaster-cli <command>
```

## Databaze

```bash
ticketmaster-cli db migrate
ticketmaster-cli db seed-dev
```

## Prvni Admin

```bash
ticketmaster-cli user create-internal \
  --email admin@example.com \
  --name "Admin" \
  --role Admin
```

## Uzivatele

```bash
ticketmaster-cli user list
ticketmaster-cli user deactivate --email old@example.com
```

Interni role:

- `Admin`
- `DeliveryManager`
- `L1`
- `L2`
- `L3`

## Partneri a klienti

```bash
ticketmaster-cli partner create --name "Acme Partner"
ticketmaster-cli partner list
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

Partner role:

- `responsible`
- `technical`

## Tickety

```bash
ticketmaster-cli ticket show --id <ticket-id>
ticketmaster-cli ticket assign --id <ticket-id> --team L2 --assignee l2@example.test
ticketmaster-cli ticket transfer-owner --id <ticket-id> --new-owner new-owner@example.test
ticketmaster-cli ticket close --id <ticket-id>
```

Interni ticket:

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

## E-mail

```bash
ticketmaster-cli email test --to user@example.com
```

## CLI actor

CLI zapisove operace pouzivaji systemoveho uzivatele:

```text
cli-system@ticketmaster.local
```

Pokud neexistuje, CLI ho vytvori jako internal `Admin`.
