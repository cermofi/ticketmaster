# Product Guide

Tato stranka popisuje TicketMaster jako produkt: kdo ho pouziva, jake workflow podporuje a jake koncepty jsou dulezite pro spravny provoz.

## Uzivatelske skupiny

| Skupina | Role | Typicke ukoly |
| --- | --- | --- |
| Interni uzivatel | `Admin` | sprava internich uzivatelu, partneru, klientu, audit, plne opravneni k ticketum |
| Interni uzivatel | `DeliveryManager` | sprava partneru/klientu/partner uzivatelu, dohled nad tickety, audit, triaz |
| Interni uzivatel | `L1` | prvni uroven reseni, prace s prirazenymi nebo vlastnenymi tickety |
| Interni uzivatel | `L2` | druha uroven reseni, eskalace na L3 |
| Interni uzivatel | `L3` | vyvojova uroven reseni, GitLab issue workflow |
| Partner uzivatel | `responsible` | vytvareni ticketu, vlastnictvi ticketu, sprava participantu, transfer ownera |
| Partner uzivatel | `technical` | sledovani a komentovani ticketu, pokud je participant |

## Dulezite pojmy

### Partner

Partner reprezentuje organizaci zakaznika. Partner ma aktivni/neaktivni stav, vlastni uzivatele a klienty. Deaktivace partnera je blokovana, pokud existuji aktivni klienti, aktivni partner uzivatele nebo neuzavrene tickety.

### Client

Client je konkretni zakaznicky subjekt nebo system v ramci partnera. Odpovedne osoby partnera mohou byt prirazeny ke klientum. Pri vytvareni partner ticketu s klientem musi byt owner ticketu odpovednou osobou pro dany klient.

### Ticket

Ticket je hlavni pracovni jednotka. Obsahuje typ, prioritu, status, ownera, creator, partnera, klienta, resitelsky tym, assignee, popis, komentare, prilohy, participanty, watchery a auditni historii.

### Participant

Participant je partner uzivatel, ktery muze videt komunikaci a pridavat komentare do partner ticketu. Owner je automaticky participant a nelze ho odebrat.

### Watcher

Watcher dostava notifikace. Participant je automaticky pridany i jako watcher. Interni assignee se take pridava jako watcher.

### Internal ticket

Interni ticket nema partnera ani klienta. Vytvari ho interni uzivatel a creator se stava ownerem. Owner vidi ticket i v pripade, ze nespada do jeho resitelskeho tymu.

## Ticket typy

Podporovane typy:

- `Problem`
- `Change Request`
- `New Feature`
- `Question`
- `Configuration`
- `Integration`
- `Security Issue`
- `Operational Request`

U typu `Security Issue` se priorita `Normal` automaticky povysuje na `Critical`.

## Priority

Podporovane priority:

- `Low`
- `Normal`
- `High`
- `Critical`

Priority jsou pouzivane pro filtrovani, prehled v dashboardu a zvyrazneni v UI.

## Statusy

Podporovane statusy:

- `New`
- `Need more info`
- `Assigned`
- `In progress`
- `Resolved`
- `Closed`
- `Rejected`
- `Duplicate`
- `Cancelled`

Workflow prechody a opravneni jsou popsane na strance [RBAC & Workflow](rbac.md).

## Zivotni cyklus partner ticketu

1. Odpovedna osoba partnera vytvori ticket.
2. Ticket zacina ve stavu `New`.
3. Delivery Manager nebo Admin provede triaz a priradi ticket na `L1`, `L2` nebo `L3`.
4. Resitelsky tym meni stav podle povoleneho workflow.
5. Partner participanti a interni uzivatele komunikuji v detailu ticketu.
6. Interni uzivatele mohou pridavat internal notes, ktere partner nevidi.
7. Po vyreseni se ticket presune na `Resolved`.
8. Ticket se uzavre jako `Closed`.

## Zivotni cyklus internal ticketu

1. Interni uzivatel vytvori internal ticket.
2. Creator se stane ownerem.
3. Pokud je vybran resitelsky tym, ticket zacina jako `Assigned`; jinak jako `New`.
4. Owner vidi ticket nezavisle na resitelskem tymu.
5. Pokud je ticket prirazen na `L3`, system se pokusi zalozit GitLab issue.
6. Ticket pokracuje standardnim internim workflow.

## Uzavrene tickety

U uzavreneho ticketu se ve web UI nezobrazuje formular pro pridani komentare ani internal note. API ochrana zustava zachovana a pri pokusu o zapis do uzavreneho ticketu vraci validacni chybu.

