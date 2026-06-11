# RBAC & Workflow

Detailni pravidla jsou v [aplikacni logice](ticketmaster_aplikacni_logika.md). Tato stranka je rychla orientace pro vyvojare.

## Role

| Role | Typ | Smysl |
| --- | --- | --- |
| `Admin` | internal | plna sprava a vsechny tickety |
| `DeliveryManager` | internal | sprava bez internich Admin uctu, triaz, audit |
| `L1` | internal | resi tickety teamu L1 |
| `L2` | internal | resi tickety teamu L2 |
| `L3` | internal | resi tickety teamu L3 s GitLab guardem |
| `responsible` | partner | zaklada partner tickety, komentuje system tickety partnera |
| `technical` | partner | komentuje partner ticket pouze jako participant |

## Viditelnost

- Admin a Delivery Manager vidi vsechny tickety.
- L1/L2/L3 vidi jen tickety sveho `resolver_team`.
- Partner vidi partner a system tickety sveho partnera.
- Partner nevidi interni tickety ani interni poznamky.
- System ticket vidi interní resolver role jen pokud odpovida jeho `resolver_team`.

## Komunikace

- Closed ticket nejde komentovat ani doplnovat interni poznamkou.
- Komentare a interni poznamky se needituji a nemazou.
- Partner `technical` nemuze komentovat system ticket.
- Partner `responsible` muze komentovat system ticket sveho partnera.

## Workflow

| Z | Do |
| --- | --- |
| `New` | `Need more info`, `Assigned`, `Rejected`, `Duplicate`, `Cancelled` |
| `Need more info` | `New`, `Assigned`, `Rejected`, `Cancelled` |
| `Assigned` | `In progress`, `Need more info`, `Cancelled` |
| `In progress` | `Resolved`, `Need more info`, `Assigned` |
| `Resolved` | `Closed` |
| `Rejected` | `Closed` |
| `Duplicate` | `Closed` |
| `Cancelled` | `Closed` |
| `Closed` | zadny prechod |

Closed je finalni a uzavirat smi jen Admin nebo Delivery Manager.

## Assignment

- Resolver team se po nastaveni nemeni.
- Menit lze jen assignee v ramci stejneho teamu.
- Admin nebo Delivery Manager muze ticket vratit do fronty stejneho teamu.
- Bez GitLab issue nelze priradit ticket na L3.
