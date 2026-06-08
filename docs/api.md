# API Reference

Backend API bezi jako FastAPI aplikace. V Docker stacku je dostupne pres frontend proxy na `/api`.

## Obecna pravidla

### Base URL

```text
/api
```

### Autentizace

Chranene endpointy vyzaduji bearer token:

```http
Authorization: Bearer <token>
```

Token vraci login endpointy. Frontend ho uklada do `localStorage`.

### Error format

Business chyby vraci JSON:

```json
{"detail":"Human readable error message"}
```

Typicke status kody:

| Status | Vyznam |
| --- | --- |
| `400` | validacni chyba nebo konflikt workflow |
| `401` | chybejici/neplatna autentizace |
| `403` | nedostatecne opravneni |
| `404` | entita neexistuje |
| `409` | konflikt business pravidel |
| `429` | prilis mnoho login pokusu |
| `500` | neocekavana chyba |

## Public/system endpointy

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/health` | jednoducha liveness odpoved |
| `GET` | `/api/ready` | readiness vcetne DB checku |
| `GET` | `/api/meta` | ticket typy, priority, statusy a resolver tymy |
| `GET` | `/metrics` | Prometheus metriky |

## Auth

### Partner login

```http
POST /api/auth/login
```

Request:

```json
{
  "email": "responsible@acme.example",
  "password": "ChangeMe123!"
}
```

Response:

```json
{
  "token": "...",
  "user": {
    "id": "...",
    "email": "responsible@acme.example",
    "kind": "partner",
    "partner_role": "responsible"
  }
}
```

### Internal dev SSO

```http
POST /api/auth/dev-sso
```

Request:

```json
{"email":"admin@example.test"}
```

### Aktivace pozvanky

```http
POST /api/auth/activate
```

Request:

```json
{
  "token": "invitation-token",
  "password": "new-password"
}
```

### Aktualni uzivatel

```http
GET /api/auth/me
```

## Tickets

### List ticketu

```http
GET /api/tickets
```

Query parametry:

| Parametr | Popis |
| --- | --- |
| `search` | fulltext pres ticket ID/title/description/comments |
| `status` | presny status |
| `priority` | presna priorita |
| `type` | presny ticket type |
| `resolver_team` | `L1`, `L2`, `L3` |
| `partner_id` | filtr partnera pro interni uzivatele |
| `internal` | `true`/`false` |
| `limit` | pocet zaznamu, default `50`, max `200` |
| `offset` | offset pro strankovani |

Response:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

### Vytvoreni partner ticketu

```http
POST /api/tickets
```

Request:

```json
{
  "type": "Question",
  "priority": "Normal",
  "title": "Question title",
  "description": "Detailed description",
  "client_id": "optional-client-id",
  "participant_ids": []
}
```

Vyuzitelne pouze pro partner `responsible`.

### Vytvoreni internal ticketu

```http
POST /api/tickets/internal
```

Request:

```json
{
  "type": "Operational Request",
  "priority": "Normal",
  "title": "Internal title",
  "description": "Detailed description",
  "team": "L1"
}
```

### Detail ticketu

```http
GET /api/tickets/{ticket_id}
```

Vraci ticket vcetne detailu, participantu a `available_transitions`.

### Komentare

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/tickets/{ticket_id}/comments` | seznam viditelnych komentaru |
| `POST` | `/api/tickets/{ticket_id}/comments` | pridani verejneho komentare |
| `POST` | `/api/tickets/{ticket_id}/internal-notes` | pridani interni poznamky |
| `PATCH` | `/api/comments/{comment_id}` | editace komentare Admin/DeliveryManager |
| `DELETE` | `/api/comments/{comment_id}` | soft delete komentare Admin/DeliveryManager |
| `GET` | `/api/comments/{comment_id}/revisions` | historie komentare pro interni uzivatele |

Request pro komentar:

```json
{"body":"Comment text"}
```

### Participanti

| Method | Path | Popis |
| --- | --- | --- |
| `POST` | `/api/tickets/{ticket_id}/participants` | pridat participanta |
| `DELETE` | `/api/tickets/{ticket_id}/participants/{user_id}` | odebrat participanta |

Request:

```json
{"user_id":"user-id"}
```

### Assignment a workflow

| Method | Path | Popis |
| --- | --- | --- |
| `POST` | `/api/tickets/{ticket_id}/assign` | prirazeni resolver tymu a volitelne assignee |
| `POST` | `/api/tickets/{ticket_id}/transition` | zmena statusu |
| `POST` | `/api/tickets/{ticket_id}/transfer-owner` | transfer partner ownera |
| `POST` | `/api/tickets/{ticket_id}/close` | uzavreni ticketu |

Assignment request:

```json
{"team":"L2","assignee":"l2@example.test"}
```

Transition request:

```json
{"status":"In progress"}
```

Transfer owner request:

```json
{"new_owner":"new-owner@example.test"}
```

### Prilohy

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/tickets/{ticket_id}/attachments` | seznam priloh |
| `POST` | `/api/tickets/{ticket_id}/attachments` | multipart upload |
| `GET` | `/api/attachments/{attachment_id}/download` | download prilohy |

Upload omezeni:

- maximalne 25 MB,
- pripony `.png`, `.jpg`, `.jpeg`, `.pdf`, `.txt`, `.log`, `.zip`,
- ClamAV scan pred ulozenim.

## Admin API

Admin API je chranene rolemi `Admin` a `DeliveryManager`, s nekterymi operacemi pouze pro `Admin`.

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/partners` | seznam partneru |
| `POST` | `/api/partners` | vytvoreni partnera |
| `DELETE` | `/api/partners/{partner_id}` | deaktivace partnera |
| `GET` | `/api/clients` | seznam klientu |
| `POST` | `/api/clients` | vytvoreni klienta |
| `PATCH` | `/api/clients/{client_id}` | uprava klienta |
| `DELETE` | `/api/clients/{client_id}` | deaktivace klienta |
| `POST` | `/api/client-assignments` | prirazeni odpovedne osoby ke klientovi |
| `GET` | `/api/client-assignments?client_id=...` | seznam prirazeni |
| `DELETE` | `/api/client-assignments/{assignment_id}` | odebrani prirazeni |
| `GET` | `/api/users` | seznam uzivatelu |
| `POST` | `/api/users/internal` | vytvoreni interniho uzivatele |
| `POST` | `/api/users/partner` | pozvani partner uzivatele |
| `PATCH` | `/api/users/{user_id}` | uprava uzivatele |
| `DELETE` | `/api/users/{user_id}` | deaktivace uzivatele |
| `POST` | `/api/users/{user_id}/password-reset` | password reset |

## Audit API

```http
GET /api/audit
GET /api/audit?entity_id=<id>
```

Dostupne pouze pro `Admin` a `DeliveryManager`.

## GitLab API

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/gitlab/check` | kontrola konfigurace |
| `POST` | `/api/tickets/{ticket_id}/gitlab/create-issue` | zalozeni GitLab issue |
| `POST` | `/api/tickets/{ticket_id}/gitlab/sync-status` | synchronizace GitLab statusu |

## Notifications API

| Method | Path | Popis |
| --- | --- | --- |
| `POST` | `/api/email/test?to=user@example.com` | test SMTP |
| `POST` | `/api/notifications/retry-failed` | manualni retry notifikaci |

