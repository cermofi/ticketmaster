# API Reference

Backend API bezi jako FastAPI aplikace a pres frontend proxy je dostupne na `/api`.

## Autentizace

Chranene endpointy vyzaduji:

```http
Authorization: Bearer <token>
```

Chyby vraci JSON:

```json
{"detail":"Human readable error message"}
```

## System endpointy

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/health` | liveness |
| `GET` | `/api/ready` | readiness vcetne DB |
| `GET` | `/api/meta` | typy, priority, statusy, resolver teamy |

## Auth

| Method | Path | Popis |
| --- | --- | --- |
| `POST` | `/api/auth/login` | partner login e-mailem a heslem |
| `POST` | `/api/auth/dev-sso` | dev SSO pro interni uzivatele |
| `POST` | `/api/auth/activate` | aktivace/reset hesla tokenem |
| `GET` | `/api/auth/me` | aktualni uzivatel |

Neaktivni uzivatel se nemuze prihlasit ani provadet aktivni akce.

## Tickets

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/tickets` | list viditelnych ticketu |
| `POST` | `/api/tickets` | vytvoreni partner ticketu odpovednou osobou |
| `POST` | `/api/tickets/internal` | vytvoreni interniho ticketu |
| `GET` | `/api/tickets/{ticket_id}` | detail ticketu |
| `POST` | `/api/tickets/{ticket_id}/comments` | verejny komentar |
| `POST` | `/api/tickets/{ticket_id}/internal-notes` | interni poznamka |
| `POST` | `/api/tickets/{ticket_id}/assign` | prirazeni teamu/asignee |
| `POST` | `/api/tickets/{ticket_id}/unassign` | vraceni do fronty stejneho teamu |
| `POST` | `/api/tickets/{ticket_id}/transition` | zmena statusu |
| `POST` | `/api/tickets/{ticket_id}/close` | uzavreni Admin/Delivery Manager |
| `POST` | `/api/tickets/{ticket_id}/participants` | pridani partner osoby |
| `DELETE` | `/api/tickets/{ticket_id}/participants/{user_id}` | odebrani partner osoby |
| `GET` | `/api/tickets/{ticket_id}/attachments` | prilohy |
| `POST` | `/api/tickets/{ticket_id}/attachments` | upload prilohy |

Editace a mazani komentaru i internich poznamek jsou v MVP zakazane.

## Jednoduche partnerske API

Prvni verze API podporuje pouze list ticketu partnera a vytvoreni system ticketu pro partnera. API nevytvari partner ticket.

Aktualni technicke rozhodnuti MVP: API pouziva stejny Bearer token jako UI. Samostatne API klice nejsou soucasti MVP.

### List ticketu partnera

```http
GET /api/partner-api/partners/{partner_id}/tickets
```

Query parametry:

| Parametr | Popis |
| --- | --- |
| `status` | volitelny status |
| `priority` | volitelna priorita |
| `type` | volitelny typ ticketu |
| `limit` | velikost stranky |
| `offset` | offset |

### Vytvoreni system ticketu

```http
POST /api/partner-api/partners/{partner_id}/tickets
```

```json
{
  "type": "Operational Request",
  "priority": "Normal",
  "title": "Integration event",
  "description": "Event description",
  "team": "L1",
  "assignee": null
}
```

System ticket:

- patri pod konkretniho partnera,
- nema klienta, vlastnika ani autora,
- ma `system: true`,
- partner ho vidi cely,
- za partnera ho smi komentovat pouze odpovedna osoba,
- interně ho vidi Admin, Delivery Manager a resolver role podle `resolver_team`.

## Admin

| Method | Path | Popis |
| --- | --- | --- |
| `GET` | `/api/partners` | list partneru |
| `POST` | `/api/partners` | vytvoreni partnera |
| `GET` | `/api/clients` | list klientu |
| `POST` | `/api/clients` | vytvoreni klienta |
| `PATCH` | `/api/clients/{client_id}` | uprava klienta |
| `GET` | `/api/users` | list uzivatelu |
| `POST` | `/api/users/internal` | vytvoreni interniho uzivatele |
| `POST` | `/api/users/partner` | pozvani partner uzivatele |
| `PATCH` | `/api/users/{user_id}` | uprava uzivatele vcetne active |
| `DELETE` | `/api/users/{user_id}` | deaktivace uzivatele |
| `POST` | `/api/users/{user_id}/password-reset` | reset hesla |
| `POST` | `/api/client-assignments` | prirazeni odpovedne osoby ke klientovi |
| `DELETE` | `/api/client-assignments/{assignment_id}` | odebrani odpovedne osoby |

Partneri a klienti se v MVP nemazou a nemaji active/inactive stav.
