# RBAC & Workflow

RBAC je vynuceny v service vrstve backendu. UI skryva akce, ktere uzivatel nema mit k dispozici, ale rozhodujici ochrana zustava na API.

## Role

| Role | Typ uzivatele | Popis |
| --- | --- | --- |
| `Admin` | internal | plna sprava aplikace |
| `DeliveryManager` | internal | sprava partneru/klientu/partner uzivatelu, triaz a audit |
| `L1` | internal | reseni L1 ticketu |
| `L2` | internal | reseni L2 ticketu |
| `L3` | internal | vyvojove reseni a GitLab workflow |
| `responsible` | partner | owner partner ticketu, vytvareni ticketu, sprava participantu |
| `technical` | partner | technicky participant bez moznosti vytvaret ticket |

## Viditelnost ticketu

| Uzivatel | Vidi ticket kdyz |
| --- | --- |
| `Admin` | vzdy |
| `DeliveryManager` | vzdy |
| `L1/L2/L3` | ticket ma stejny `resolver_team`, assignee z jejich tymu nebo je uzivatel owner |
| Partner `responsible` | ticket patri jeho partnerovi a neni internal |
| Partner `technical` | ticket patri jeho partnerovi a neni internal |

Poznamka: Partner viditelnost je na urovni partnera, ale komentovat muze jen participant.

## Komentovani

| Akce | Opravneni |
| --- | --- |
| Verejny komentar | interni uzivatel s view opravnenim nebo partner participant |
| Internal note | interni uzivatel s view opravnenim |
| Komentar na `Closed` ticketu | zakazano |
| Editace komentare | `Admin` nebo `DeliveryManager` |
| Soft delete komentare | `Admin` nebo `DeliveryManager` |
| Historie komentare | interni uzivatel |

## Participant management

Participanty lze menit pouze u partner ticketu.

| Akce | Opravneni |
| --- | --- |
| Pridat participanta | partner owner, `Admin`, `DeliveryManager` |
| Odebrat participanta | partner owner, `Admin`, `DeliveryManager` |
| Odebrat ownera z participantu | zakazano |
| Sprava participantu u internal ticketu | zakazano |

Partner `technical` vidi participanty, ale nema tlacitka ani API opravneni ke zmene.

## Vytvareni ticketu

| Akce | Opravneni |
| --- | --- |
| Partner ticket | partner `responsible` |
| Internal ticket | `Admin`, `DeliveryManager`, `L1`, `L2`, `L3` |
| Partner ticket pro klienta | owner musi byt odpovedna osoba pro klienta |
| Partner `technical` vytvari ticket | zakazano |

## Assignment

| Akce | Opravneni |
| --- | --- |
| Libovolne prirazeni | `Admin`, `DeliveryManager` |
| L1 -> L2 | `L1`, pokud ticket patri do L1 |
| L2 -> L3 | `L2`, pokud ticket patri do L2 |
| Jine eskalace resolver rolemi | zakazano |

Assignee musi byt aktivni interni uzivatel ze stejneho resitelskeho tymu.

## Workflow prechody

| Z | Do |
| --- | --- |
| `New` | `Need more info`, `Assigned`, `Rejected`, `Duplicate`, `Cancelled` |
| `Need more info` | `Assigned`, `Rejected`, `Cancelled` |
| `Assigned` | `In progress`, `Need more info`, `Cancelled` |
| `In progress` | `Resolved`, `Need more info`, `Assigned` |
| `Resolved` | `Closed` |
| `Rejected` | `Closed` |
| `Duplicate` | `Closed` |
| `Cancelled` | `Closed` |
| `Closed` | zadny prechod |

## Transition permission

Partner uzivatele v MVP nemohou menit status ticketu.

Interni pravidla:

- `Admin` a `DeliveryManager` mohou provadet povolene workflow prechody.
- `L1`, `L2`, `L3` mohou menit status ticketu sveho resolver tymu na `In progress`, `Resolved`, `Need more info`, `Assigned`, `Closed`.
- `Closed` ticket je finalni a nema dalsi transition.

## L3 a GitLab guard

Ticket prirazeny na `L3` musi mit GitLab issue pred prechodem do `In progress`. Pokud issue neexistuje a neni explicitne prepsany GitLab error stav, API vrati konflikt.

## Deaktivace

### Partner

Partnera lze deaktivovat jen pokud:

- nema aktivni klienty,
- nema aktivni partner uzivatele,
- nema neuzavrene tickety.

### Uzivatel

Pravidla:

- uzivatel nemuze deaktivovat sam sebe,
- nelze odstranit posledniho aktivniho `Admin`,
- deaktivace smaze invitation token.

