# TicketMaster - finální vývojový plán MVP

## 0. Účel dokumentu

Tento dokument je finální zadání pro vývoj MVP aplikace **TicketMaster**.

Cílem je, aby vývojový tým dokázal podle dokumentu navrhnout, implementovat a otestovat aplikaci bez nutnosti domýšlet procesní pravidla.

Dokument nahrazuje původní produktový návrh a převádí ho do vývojového plánu. Obsahuje:

- popis cíle MVP,
- role a oprávnění,
- proces ticketu,
- datový model na úrovni entit,
- funkční požadavky,
- GitLab integraci,
- notifikace,
- audit,
- dashboardy,
- aplikační CLI pro správu aplikace z Docker kontejneru,
- technický backlog rozdělený na etapy,
- akceptační kritéria MVP.

## 1. Shrnutí produktu

TicketMaster je interně spravovaný ticketovací systém pro komunikaci mezi partnery TeskaLabs, interním týmem a řešitelskými odděleními.

Externí přístup mají v MVP pouze uživatelé partnerů. Koncoví klienti do MVP přímo nepřistupují.

Hlavní princip:

- partner zakládá požadavky přes odpovědnou osobu partnera,
- Delivery Manager provádí vstupní kontrolu a směrování,
- řešení následně přebírá L1 / L2 / L3,
- L3 ticket musí mít GitLab issue,
- GitLab status je viditelný i partnerovi jako doplňková informace,
- GitLab link zůstává interní,
- interní tickety jsou součástí MVP v jednoduché podobě.

## 2. Rozsah MVP

### 2.1 Součást MVP

- Přihlášení interních uživatelů přes SSO.
- Přihlášení externích uživatelů partnera přes e-mail a heslo.
- Zakládání externích účtů přes pozvánku e-mailem.
- Správa partnerů, uživatelů partnera, klientů a vazeb klient ↔ odpovědná osoba.
- Role: Odpovědná osoba partnera, Technická osoba partnera, Delivery Manager, L1, L2, L3, Admin.
- Partnerské tickety.
- Interní tickety v jednoduché podobě.
- Vlastník ticketu a převod vlastnictví.
- Komunikace v ticketu přes komentáře.
- Interní poznámky.
- Přílohy.
- Workflow ticketu.
- E-mailové notifikace.
- Audit log viditelný v UI pro Admina a Delivery Managera.
- GitLab integrace pro L3.
- Partner dashboard.
- Interní dashboard.
- Admin část.
- Permission matrix podle tohoto dokumentu.
- Aplikační CLI dostupné přes binárku v Docker kontejneru pro základní administraci a provozní úkony.

### 2.2 Není součást MVP

- SLA pravidla.
- SLA dashboard.
- Reportování času.
- Evidence placeného vývoje.
- Kanban pohled.
- Pokročilá pravidla oprávnění nad rámec tohoto dokumentu.
- Automatické uzavírání ticketů po určité době bez reakce partnera.
- Reopen uzavřeného ticketu.
- Pokročilé notifikační preference.
- L1 AI agent.
- Přístup koncových klientů do systému.

### 2.3 Otevřené body mimo MVP implementaci

Tyto body nejsou blokátorem pro začátek vývoje, ale musí zůstat explicitně označené:

- Finální formát ID ticketu.
- Přesný název / ID GitLab projektu, do kterého se budou automaticky vytvářet L3 issue.
- Přesné technické nastavení SSO provideru.
- Přesné SMTP nastavení pro odesílání e-mailů.

## 3. Terminologie

| Pojem | Význam |
|---|---|
| TicketMaster | Název aplikace. |
| Partner | Partnerská firma nebo partnerská skupina. |
| Klient | Klient partnera evidovaný v systému. Koncový klient se do MVP nepřihlašuje. |
| Odpovědná osoba partnera | Uživatel partnera, který může zakládat tickety a řídit komunikaci za partnera. |
| Technická osoba partnera | Technický kontakt partnera. Ticket nezakládá, ale může komentovat ticket, kam byla přidána. |
| Vlastník ticketu | Odpovědná osoba partnera, která ticket založila, nebo na kterou bylo vlastnictví převedeno. |
| Delivery Manager | Interní role odpovědná za vstupní kontrolu, směrování a eskalace. |
| L1 - Service Desk | První úroveň podpory. |
| L2 - Application Support | Druhá úroveň podpory. |
| L3 - Development | Vývojová úroveň řešení. |
| Assignee | Konkrétní interní uživatel přiřazený k řešení ticketu. |
| Resolver team | Řešitelské oddělení L1 / L2 / L3. |
| GitLab issue | Vývojové issue vytvořené pro L3 ticket. |
| GitLab status | Doplňkový technický stav GitLab issue viditelný interně i partnerovi. |
| GitLab link | Odkaz na GitLab issue, viditelný pouze internímu týmu. |
| Internal ticket | Interní ticket bez vazby na partnera. |

## 4. Uživatelé, role a přístup

### 4.1 Přihlášení

Aplikace musí podporovat kombinovaný model přihlášení.

| Typ uživatele | Přihlášení | Poznámka |
|---|---|---|
| Interní uživatelé TeskaLabs | SSO přes firemní identity provider | Primární způsob přihlášení pro interní tým. |
| Externí uživatelé partnera | E-mail + heslo | Účet vzniká přes pozvánku e-mailem. |
| Externí uživatelé partnera | Pozvánka e-mailem + nastavení hesla | Uživatel si heslo nastaví při aktivaci účtu. |
| Koncoví klienti | Bez přístupu v MVP | Koncoví klienti se do systému v MVP nepřihlašují. |

### 4.2 Správa uživatelů

Uživatele partnera mohou zakládat a spravovat:

- Admin,
- Delivery Manager.

Odpovědná osoba partnera v MVP nesmí sama vytvářet nové uživatele partnera. Může pouze přidávat existující uživatele stejného partnera do komunikace ticketu.

### 4.3 Interní viditelnost podle oddělení

Delivery Manager a Admin vidí všechny tickety.

L1 / L2 / L3 nevidí automaticky všechny tickety. Uživatelé řešitelských oddělení vidí:

- frontu svého oddělení,
- tickety, kde je resolver_team jejich oddělení,
- tickety, kde je assignee členem jejich oddělení.

Příklad:

- uživatel L1 vidí L1 frontu,
- uživatel L2 vidí L2 frontu,
- uživatel L3 vidí L3 frontu,
- uživatel L1 nevidí běžně L3 frontu,
- Delivery Manager a Admin vidí vše.

### 4.4 L3 uživatel není samostatná role Developer

Pojem Developer se nepoužívá jako samostatná role.

Uživatel oddělení L3 je běžný interní uživatel zařazený do řešitelského oddělení L3 - Development. Může být assignee konkrétního ticketu a má práva podle permission matrix pro L1/L2/L3.

## 5. Partner, klient a odpovědné osoby

### 5.1 Partner

Partner je firma nebo partnerská skupina. Všichni uživatelé partnera patří právě pod jednoho partnera.

Uživatel partnera nikdy nevidí tickety jiného partnera.

### 5.2 Klient

Klient vždy patří ke konkrétnímu partnerovi.

Ticket může být:

- navázaný na konkrétního klienta,
- bez klienta.

Klient je při založení ticketu volitelný.

### 5.3 Vazba klient ↔ odpovědná osoba

Vztah mezi klienty a odpovědnými osobami je mnoho ku mnoha.

Platí:

- jeden klient může mít více odpovědných osob,
- jedna odpovědná osoba může mít více klientů,
- vazba platí pouze uvnitř stejného partnera.

## 6. Typy ticketů a priority

### 6.1 Finální typy ticketů

| Ticket type | Vysvětlení pro uživatele | Doporučené oddělení | Výchozí priorita |
|---|---|---|---|
| Problem | Něco nefunguje správně nebo se systém chová jinak, než má. | L2 / L3 | Normal |
| Change Request | Požadavek na změnu chování systému nebo úpravu existující funkce. | L3 | Normal |
| New Feature | Požadavek na novou funkcionalitu. | L3 | Normal |
| Question | Dotaz k fungování systému nebo žádost o vysvětlení. | L1 | Normal |
| Configuration | Požadavek na změnu nastavení, konfigurace nebo oprávnění. | L2 | Normal |
| Integration | Požadavek týkající se napojení na jiný systém. | L2 / L3 | Normal |
| Security Issue | Podezření na zranitelnost, únik dat nebo jiný bezpečnostní problém. | dle posouzení DM | Critical |
| Operational Request | Jednoduchý provozní požadavek, který nevyžaduje vývoj ani hlubší analýzu. | L1 | Normal |

### 6.2 Priority

Finální priority:

- Low,
- Normal,
- High,
- Critical.

Partner při založení ticketu vybírá prioritu. Delivery Manager může prioritu změnit při vstupní kontrole.

Security Issue má výchozí prioritu Critical, ale Delivery Manager ji může podle obsahu ticketu upravit.

## 7. Vlastník ticketu a převod vlastnictví

### 7.1 Vlastník ticketu

Každý partnerský ticket má jednoho vlastníka.

Vlastníkem ticketu je odpovědná osoba partnera, která ticket založila.

Vlastník ticketu:

- je primární kontakt za partnera,
- je automaticky účastníkem komunikace,
- je automaticky sledovatel ticketu,
- dostává notifikace k ticketu,
- může přidávat a odebírat osoby z komunikace,
- může převést vlastnictví ticketu podle pravidel níže.

### 7.2 Převod vlastnictví

Převod vlastnictví může provést:

- Admin,
- Delivery Manager,
- aktuální vlastník ticketu.

Ticket lze převést pouze na:

- odpovědnou osobu stejného partnera,
- která má vazbu na daného klienta, pokud je ticket navázaný na klienta.

Pokud je ticket bez klienta, lze vlastnictví převést na jinou odpovědnou osobu stejného partnera.

Při převodu:

- nová odpovědná osoba se stane vlastníkem ticketu,
- nová odpovědná osoba se automaticky přidá do komunikace,
- původní vlastník může v komunikaci zůstat nebo být odebrán,
- změna se zapíše do auditu.

## 8. Viditelnost a komentování

### 8.1 Viditelnost partnera

Uživatel partnera vidí tickety v rámci svého partnera včetně:

- seznamu ticketů,
- detailu ticketu,
- komentářů,
- příloh,
- základní historie,
- GitLab statusu, pokud ticket GitLab issue má.

Uživatel partnera nikdy nevidí ticket jiného partnera.

### 8.2 Právo komentovat

Viditelnost ticketu není totéž jako právo komentovat.

Komentovat smí pouze uživatel partnera, který je přidaný do komunikace daného ticketu.

Technická osoba partnera:

- vidí tickety svého partnera,
- komentovat může jen ticket, kam byla přidána,
- nemůže založit ticket,
- nemůže změnit typ, klienta, prioritu, stav ani resolver team,
- nemůže přidávat ani odebírat osoby z komunikace.

### 8.3 Interní poznámky

Internal note vidí pouze interní tým.

Partner nikdy nevidí interní poznámky.

## 9. Workflow ticketu

### 9.1 Hlavní workflow

Hlavní workflow:

New -> Need more info -> Assigned -> In progress -> Resolved -> Closed

Vedlejší stavy:

- Rejected,
- Duplicate,
- Cancelled.

### 9.2 Význam stavů

| Stav | Význam | Odpovědnost |
|---|---|---|
| New | Nový ticket čeká na kontrolu. | Delivery Manager |
| Need more info | Chybí informace od partnera. Požadavek na doplnění jde všem účastníkům komunikace za stranu partnera. | Partner |
| Assigned | Ticket je přiřazen na L1 / L2 / L3. Od tohoto stavu má povinně resolver_team. | Delivery Manager |
| In progress | Ticket řeší přiřazené oddělení nebo konkrétní assignee. | L1 / L2 / L3 |
| Resolved | Ticket je vyřešený. | Řešitelské oddělení |
| Closed | Ticket je ručně uzavřený. Automatické uzavírání není součástí MVP. | Řešitelské oddělení / Delivery Manager / Admin |
| Rejected | Ticket nebude řešen. | Delivery Manager |
| Duplicate | Ticket je duplicitní. | Delivery Manager |
| Cancelled | Ticket byl zrušen nebo už není relevantní. | Interní tým |

### 9.3 Povolené přechody stavů

| Aktuální stav | Možný další stav | Kdo |
|---|---|---|
| New | Need more info / Assigned / Rejected / Duplicate / Cancelled | Delivery Manager |
| Need more info | Assigned / Rejected / Cancelled | Delivery Manager |
| Assigned | In progress / Need more info / Cancelled | Řešitel / řešitelské oddělení / Delivery Manager |
| In progress | Resolved / Need more info / Assigned | Řešitelské oddělení |
| Resolved | Closed | Řešitelské oddělení / Delivery Manager |
| Closed | bez standardního přechodu | otevřený bod pro budoucí reopen |
| Rejected | Closed | Delivery Manager |
| Duplicate | Closed | Delivery Manager |
| Cancelled | Closed | Delivery Manager / Admin |

### 9.4 Reopen

Reopen není součástí MVP.

Uzavřený ticket zůstává uzavřený. Pokud se objeví nový problém, založí se nový ticket.

## 10. Proces zpracování ticketu

### 10.1 Založení ticketu

Ticket může založit pouze odpovědná osoba partnera.

Při založení se vyplňuje:

- typ ticketu,
- klient nebo bez klienta,
- priorita,
- název ticketu,
- popis,
- přílohy volitelně,
- osoby přidané do komunikace volitelně.

Uživatel, který ticket založí, se automaticky stává vlastníkem ticketu.

### 10.2 Kontrola Delivery Managerem

Delivery Manager může:

- vyžádat doplnění,
- upravit typ ticketu,
- upravit klienta,
- upravit prioritu,
- zamítnout ticket,
- označit ticket jako duplicitu,
- přiřadit ticket na resolver team.

### 10.3 Need more info

Při přechodu do Need more info se požadavek na doplnění odešle všem účastníkům komunikace za stranu partnera.

Interní uživatel musí doplnit komentář s tím, jaké informace chybí.

Po doplnění informací může Delivery Manager posunout ticket rovnou do Assigned.

### 10.4 Assigned a resolver team

Od stavu Assigned má ticket povinné pole resolver_team.

Ticket může mít volitelné pole assignee.

- resolver_team určuje oddělení, které za ticket odpovídá,
- assignee určuje konkrétního interního uživatele, který ticket řeší,
- pokud není assignee vyplněný, ticket je ve frontě daného oddělení.

### 10.5 Řešení ticketu

Od stavu Assigned si ticket řídí příslušné řešitelské oddělení.

Delivery Manager už běžně neřídí technický průběh ticketu.

L1 může eskalovat ticket na L2 bez zásahu Delivery Managera.

L2 může eskalovat ticket na L3 bez zásahu Delivery Managera.

### 10.6 Uzavření ticketu

Po dokončení řešení přechází ticket do Resolved.

Do stavu Closed se ticket v MVP přesune ručně.

Ticket může uzavřít:

- řešitelské oddělení,
- Delivery Manager,
- Admin.

Automatické uzavírání není součástí MVP.

### 10.7 Mazání ticketů

Ticket se v MVP nesmí mazat.

Nepodporuje se hard delete ani soft delete ticketu.

Uživatelsky se používají stavy:

- Cancelled,
- Rejected,
- Closed.

## 11. Přílohy

### 11.1 Pravidla příloh

Přílohy může přidat každý uživatel, který může komentovat daný ticket.

To znamená:

- účastník komunikace za partnera,
- interní uživatel s právem komentovat ticket.

### 11.2 Limity a typy souborů

Maximální velikost jedné přílohy:

- 25 MB.

Povolené typy souborů:

- png,
- jpg / jpeg,
- pdf,
- txt,
- log,
- zip.

### 11.3 Přílohy a GitLab

Přílohy se do GitLabu automaticky neposílají.

Do GitLab issue se může uvést pouze odkaz na ticket v TicketMasteru.

GitLab link zpět na issue je viditelný pouze internímu týmu.

## 12. Komentáře a interní poznámky

### 12.1 Typy komunikace

| Typ | Viditelnost | Použití |
|---|---|---|
| Comment | Přidaní účastníci komunikace + interní tým | Běžná komunikace mezi partnerem a interním týmem. |
| Internal note | Pouze interní tým | Interní poznámky, technická domluva, poznámky pro řešení. |

### 12.2 Úpravy a mazání komentářů

Uživatelé partnera nemohou upravovat ani mazat komentáře.

Komentáře může upravovat nebo mazat pouze:

- Delivery Manager,
- Admin.

Mazání komentáře je soft delete. Komentář se fyzicky nemaže z databáze.

U upraveného nebo smazaného komentáře musí být evidováno:

- kdo změnu provedl,
- kdy byla změna provedena.

Historie změn komentáře musí zůstat dostupná interně.

## 13. GitLab integrace

### 13.1 Kdy vzniká GitLab issue

GitLab issue musí vzniknout pro každý ticket přiřazený na L3 - Development.

Vytvoření GitLab issue proběhne automaticky při přiřazení ticketu na L3.

GitLab issue se vytváří vždy do jednoho pevně daného GitLab projektu.

Přesný GitLab projekt bude doplněn v konfiguraci.

### 13.2 Pravidla GitLab vazby

- Jeden ticket může mít maximálně jedno hlavní GitLab issue.
- Další GitLab odkazy mohou existovat pouze jako související odkazy.
- Hlavní GitLab issue je to, jehož stav se zobrazuje u ticketu.
- GitLab link vidí pouze interní tým.
- GitLab status vidí interní tým i uživatelé partnera u ticketů, které vidí.

### 13.3 Selhání vytvoření GitLab issue

Pokud se vytvoření GitLab issue nepodaří:

- ticket zůstane ve stavu Assigned,
- resolver_team zůstane L3 - Development,
- systém zobrazí interní chybu,
- chyba se zapíše do audit logu,
- ticket nesmí přejít do In progress, dokud nemá GitLab issue nebo dokud interní uživatel chybu vědomě nepřeklene.

Pravidla pro vědomé překlenutí chyby zůstávají otevřený bod pro technické dopracování.

### 13.4 GitLab status

GitLab status se bere z kombinace:

- GitLab issue state,
- GitLab board list.

Jasně dané stavy GitLab statusu v TicketMasteru:

- Open,
- To Do,
- In Progress,
- Done,
- Closed.

Doporučené mapování:

| GitLab stav v TicketMasteru | Zdroj v GitLabu | Poznámka |
|---|---|---|
| Open | issue state = opened, bez odpovídající board list hodnoty | Výchozí technický stav. |
| To Do | issue state = opened + board list To Do | Issue je připravené k práci. |
| In Progress | issue state = opened + board list In Progress | Na issue se pracuje. |
| Done | issue state = opened + board list Done | Vývojově hotovo, ale ticket se nemění automaticky. |
| Closed | issue state = closed | Issue je uzavřené v GitLabu. |

GitLab status sám o sobě automaticky nemění ticketovací stav.

Přechod ticketu do Resolved provádí řešitelský tým ručně v TicketMasteru.

### 13.5 GitLab issue šablona

Přesná šablona GitLab issue zůstává otevřený bod.

Minimální doporučený obsah:

- Ticket ID,
- Ticket URL,
- Partner,
- Klient,
- Ticket type,
- Priority,
- Resolver team,
- Assignee, pokud existuje,
- Popis ticketu.

Do GitLabu se automaticky neposílají interní poznámky.

Přílohy se do GitLabu automaticky neposílají.

## 14. Interní tickety

Interní tickety jsou součástí MVP v jednoduché podobě.

Interní ticket:

- nemá partnera,
- nevidí ho žádný partner,
- může ho založit Delivery Manager, uživatel řešitelského oddělení L1 / L2 / L3 nebo Admin,
- používá stejné typy ticketů jako partnerské tickety,
- musí být jasně označen jako interní, například label `Internal`,
- může být přiřazen na L1 / L2 / L3,
- může mít stav podle stejného workflow,
- má pouze interní komunikaci,
- nemusí mít klienta.

Interní ticket v MVP nemusí mít:

- samostatné workflow,
- pokročilé typy,
- složitý approval proces,
- vazbu na partnera,
- externí notifikace.

## 15. Notifikace

V MVP budou pouze e-mailové notifikace.

Interní notifikace v aplikaci nejsou povinnou součástí MVP.

### 15.1 Sledovatelé ticketu

- Vlastník ticketu je automaticky sledovatel.
- Každý přidaný účastník komunikace je automaticky sledovatel.
- Interní assignee je automaticky sledovatel.
- Delivery Manager je sledovatel do přiřazení ticketu na oddělení.
- Po přiřazení může Delivery Manager zůstat sledovatelem, ale nemusí dostávat všechny provozní notifikace.

### 15.2 Události pro e-mailové notifikace

| Událost | Příjemce |
|---|---|
| Nový ticket | Delivery Manager |
| Ticket čeká na doplnění | Všichni účastníci komunikace za partnera |
| Nový komentář | Přidaní účastníci komunikace + interní tým podle viditelnosti ticketu |
| Změna stavu | Přidaní účastníci komunikace + odpovědné interní role |
| Ticket přiřazen na oddělení | Příslušné oddělení |
| Ticket vyřešen | Přidaní účastníci komunikace + interní tým podle viditelnosti ticketu |
| Ticket uzavřen | Přidaní účastníci komunikace |
| Uživatel přidán do komunikace | Přidaný uživatel + vlastník |
| Uživatel odebrán z komunikace | Odebraný uživatel + vlastník |

## 16. Audit log

Audit log je součástí MVP.

Audit log se musí zapisovat do databáze a musí být viditelný v UI pro:

- Admin,
- Delivery Manager.

### 16.1 Auditované události

Auditovat minimálně:

- založení ticketu,
- změnu typu ticketu,
- změnu klienta,
- změnu priority,
- změnu stavu,
- změnu resolver teamu,
- změnu assignee,
- přidání účastníka komunikace,
- odebrání účastníka komunikace,
- převod vlastnictví,
- vytvoření GitLab issue,
- chybu při vytvoření GitLab issue,
- vědomé překlenutí chyby GitLab issue,
- úpravu komentáře,
- soft delete komentáře,
- uzavření ticketu.

### 16.2 Doporučené auditní pole

| Pole | Význam |
|---|---|
| audit_id | ID auditního záznamu. |
| entity_type | Typ entity: Ticket, Comment, GitLabLink, User, Client, Partner. |
| entity_id | ID entity. |
| action | Typ akce. |
| old_value | Původní hodnota, pokud existuje. |
| new_value | Nová hodnota, pokud existuje. |
| changed_by_user_id | Kdo změnu provedl. |
| changed_at | Kdy byla změna provedena. |
| source | UI / system / GitLab sync. |

## 17. Dashboardy a UI rozsah

### 17.1 Partner dashboard

Partner dashboard obsahuje:

- seznam ticketů partnera,
- detail ticketu,
- fulltextové vyhledávání v ticketech daného partnera,
- vyhledávání podle ID a názvu,
- filtry podle stavu,
- filtry podle priority,
- filtry podle typu,
- filtry podle klienta,
- GitLab status u L3 ticketů, pokud existuje,
- možnost komentovat pouze u ticketů, kde je uživatel v komunikaci.

Partner dashboard nesmí zobrazovat:

- tickety jiného partnera,
- GitLab link,
- Internal note,
- interní auditní detaily,
- interní tickety.

### 17.2 Interní dashboard

Interní dashboard obsahuje:

- přehled ticketů podle oprávnění uživatele,
- Delivery Manager a Admin vidí všechny tickety,
- L1/L2/L3 vidí frontu svého oddělení a tickety řešené jejich oddělením,
- fulltextové vyhledávání,
- filtry podle partnera,
- filtry podle klienta,
- filtry podle vlastníka,
- filtry podle technické osoby,
- filtry podle resolver teamu,
- filtry podle assignee,
- filtr ticketů bez assignee,
- filtr podle stavu,
- filtr podle priority,
- filtr GitLab issue existuje / neexistuje,
- filtr podle GitLab statusu,
- filtr interní / partnerský ticket.

### 17.3 Admin část

Admin část obsahuje:

- správu partnerů,
- správu uživatelů partnera,
- správu klientů,
- správu vazeb klient ↔ odpovědná osoba,
- správu interních uživatelů,
- správu rolí a oprávnění,
- správu konfigurace GitLab integrace,
- přístup k audit logu.

## 18. Permission matrix

| Akce | Odpovědná osoba | Technická osoba | Delivery Manager | L1/L2/L3 | Admin |
|---|---|---|---|---|---|
| Založit partnerský ticket | ano | ne | ne | ne | ano |
| Založit interní ticket | ne | ne | ano | ano | ano |
| Vidět ticket svého partnera | ano | ano | ano | podle interních pravidel | ano |
| Vidět ticket jiného partnera | ne | ne | ano | ne | ano |
| Vidět interní ticket | ne | ne | ano | podle oddělení | ano |
| Komentovat partnerský ticket | jen pokud je v komunikaci | jen pokud je v komunikaci | ano | ano, pokud ticket vidí | ano |
| Přidat osobu do komunikace | ano | ne | ano | ne | ano |
| Odebrat osobu z komunikace | ano | ne | ano | ne | ano |
| Převést vlastnictví ticketu | ano, pokud je vlastník | ne | ano | ne | ano |
| Změnit typ ticketu | ne | ne | ano | ne | ano |
| Změnit klienta | ne | ne | ano | ne | ano |
| Změnit prioritu | ne | ne | ano | ne | ano |
| Přiřadit resolver team | ne | ne | ano | ano, při eskalaci | ano |
| Změnit Assigned na In progress | ne | ne | ano | ano | ano |
| Změnit In progress na Resolved | ne | ne | ne | ano | ano |
| Změnit Resolved na Closed | ne | ne | ano | ano | ano |
| Upravit/smazat komentář | ne | ne | ano | ne | ano |
| Vytvořit GitLab issue | ne | ne | automaticky přes systém | L3 / systém | ano |
| Vidět GitLab link | ne | ne | ano | ano, pokud ticket vidí | ano |
| Vidět GitLab status | ano | ano | ano | ano, pokud ticket vidí | ano |
| Vidět Internal note | ne | ne | ano | ano, pokud ticket vidí | ano |
| Vidět audit log | ne | ne | ano | ne | ano |
| Smazat ticket | ne | ne | ne | ne | ne |

## 19. Doporučené datové entity

| Entita | Účel |
|---|---|
| User | Společná entita pro interní i externí uživatele. |
| Partner | Partnerská firma/skupina. |
| PartnerUser | Vazba uživatele na partnera. |
| PartnerUserRole | Role uživatele partnera: odpovědná osoba / technická osoba. |
| Client | Klient partnera. |
| ClientAssignment | Vazba klienta na odpovědné osoby. |
| Ticket | Hlavní požadavek. |
| TicketOwner | Vlastník ticketu. |
| TicketOwnershipChange | Audit převodu vlastnictví ticketu. |
| TicketParticipant | Osoby přidané do komunikace ticketu. |
| TicketWatcher | Uživatelé sledující ticket a dostávající notifikace. |
| TicketType | Typ ticketu. |
| TicketTypeRouting | Doporučené výchozí oddělení pro typ ticketu. |
| TicketStatus | Stav ticketu. |
| Priority | Low / Normal / High / Critical. |
| ResolverTeam | L1 / L2 / L3. |
| Assignee | Konkrétní interní uživatel řešící ticket. |
| Attachment | Příloha ticketu nebo komentáře. |
| InternalTicket | Interní ticket bez vazby na partnera. |
| Comment | Komentář viditelný účastníkům komunikace a internímu týmu. |
| InternalNote | Interní poznámka. |
| CommentRevision | Audit úprav a soft delete komentářů. |
| GitLabLink | Vazba ticketu na GitLab issue. |
| GitLabIssueStatus | Aktuální stav GitLab issue zobrazený u ticketu pro interní tým i partnera. |
| GitLabSyncEvent | Historie synchronizace z GitLabu. |
| Notification | Evidence notifikací. |
| AuditLog | Obecný audit změn. |

## 20. Aplikační CLI

Aplikace musí mít aplikační CLI dostupné jako spustitelná binárka uvnitř Docker kontejneru backendu.

CLI slouží pro bootstrap, administraci, podporu provozu, testování a jednoduché zásahy bez ruční práce v databázi.

CLI nesmí obcházet business logiku aplikace. Příkazy musí používat stejné validační a oprávňovací vrstvy jako backend tam, kde to dává smysl.

### 20.1 Spouštění CLI

Doporučený způsob spuštění:

```bash
docker compose exec api ticketmaster-cli <command>
```

Alternativně pro jednorázové úkony:

```bash
docker compose run --rm api ticketmaster-cli <command>
```

Název služby v Docker Compose může být `api`, `backend` nebo jiný podle finální implementace. Dokumentace aplikace musí uvést přesný název služby a přesné příklady příkazů.

### 20.2 Základní požadavky na CLI

CLI musí splňovat tyto požadavky:

- je součástí backend Docker image,
- je dostupné jako binárka / executable příkaz,
- má nápovědu přes `--help`,
- vrací srozumitelné chybové hlášky,
- vrací nenulový exit code při chybě,
- podporuje idempotentní příkazy tam, kde to dává smysl,
- zapisuje audit u provozních změn, pokud se jedná o změnu aplikačních dat,
- nemá vyžadovat ruční zásah do databáze,
- nesmí vypsat citlivé tokeny, hesla ani secrets do konzole.

### 20.3 Povinné CLI příkazy pro MVP

CLI musí v MVP pokrýt minimálně následující oblasti.

#### Diagnostika a bootstrap

```bash
ticketmaster-cli health
ticketmaster-cli config check
ticketmaster-cli db migrate
ticketmaster-cli db seed-dev
```

Použití:

- ověření funkčnosti aplikace,
- kontrola konfigurace,
- spuštění databázových migrací,
- založení vývojových testovacích dat.

#### Interní uživatelé

```bash
ticketmaster-cli user create-internal --email <email> --name <name> --role <Admin|DeliveryManager|L1|L2|L3>
ticketmaster-cli user deactivate --email <email>
ticketmaster-cli user list
```

Použití:

- založení interního administrátora,
- založení Delivery Managera,
- založení uživatelů řešitelských oddělení,
- deaktivace uživatele.

Interní uživatelé se primárně přihlašují přes SSO. CLI příkaz pro vytvoření interního uživatele připraví uživatelský záznam, roli a vazbu na řešitelské oddělení.

#### Partneři, klienti a uživatelé partnera

```bash
ticketmaster-cli partner create --name <partner_name>
ticketmaster-cli partner list

ticketmaster-cli client create --partner <partner_id_or_key> --name <client_name>
ticketmaster-cli client list --partner <partner_id_or_key>

ticketmaster-cli partner-user invite --partner <partner_id_or_key> --email <email> --name <name> --role <responsible|technical>
ticketmaster-cli partner-user deactivate --email <email>
ticketmaster-cli client assign-responsible --client <client_id_or_key> --user <email_or_user_id>
```

Použití:

- založení partnera,
- založení klienta partnera,
- pozvání odpovědné osoby partnera,
- pozvání technické osoby partnera,
- přiřazení odpovědné osoby ke klientovi.

CLI musí validovat, že vazby partner / klient / odpovědná osoba dávají smysl a že se nevytváří vazba napříč partnery.

#### Tickety a provozní úkony

```bash
ticketmaster-cli ticket show --id <ticket_id>
ticketmaster-cli ticket transfer-owner --id <ticket_id> --new-owner <email_or_user_id>
ticketmaster-cli ticket assign --id <ticket_id> --team <L1|L2|L3> [--assignee <email_or_user_id>]
ticketmaster-cli ticket close --id <ticket_id>
ticketmaster-cli ticket create-internal --type <ticket_type> --priority <priority> --title <title> --description <text> [--team <L1|L2|L3>]
```

Použití:

- kontrola detailu ticketu z CLI,
- převod vlastnictví ticketu,
- interní přiřazení ticketu na resolver team,
- ruční uzavření ticketu,
- založení jednoduchého interního ticketu.

Převod vlastnictví přes CLI musí dodržovat stejná pravidla jako UI:

- nový vlastník musí být odpovědná osoba stejného partnera,
- pokud je ticket navázaný na klienta, nový vlastník musí mít vazbu na daného klienta.

#### GitLab integrace

```bash
ticketmaster-cli gitlab create-issue --ticket <ticket_id>
ticketmaster-cli gitlab sync-status --ticket <ticket_id>
ticketmaster-cli gitlab check
```

Použití:

- ruční opakování vytvoření GitLab issue po chybě,
- ruční synchronizace GitLab statusu,
- kontrola GitLab konfigurace a dostupnosti.

CLI nesmí vytvořit druhé hlavní GitLab issue pro ticket, který už hlavní GitLab issue má.

#### E-mailové notifikace

```bash
ticketmaster-cli email test --to <email>
ticketmaster-cli notifications retry-failed
```

Použití:

- otestování SMTP konfigurace,
- opětovné odeslání selhaných notifikací, pokud bude evidence selhaných notifikací implementovaná.

### 20.4 Bezpečnost a audit CLI

CLI příkazy měnící aplikační data musí být auditované.

Auditovat minimálně:

- vytvoření interního uživatele,
- deaktivaci uživatele,
- vytvoření partnera,
- vytvoření klienta,
- pozvání uživatele partnera,
- přiřazení odpovědné osoby ke klientovi,
- převod vlastnictví ticketu,
- přiřazení ticketu na resolver team,
- změnu assignee,
- ruční vytvoření GitLab issue,
- ruční synchronizaci GitLab statusu,
- ruční uzavření ticketu.

U CLI akcí musí být v auditu rozlišitelné, že změna přišla z CLI.

Doporučená hodnota pole `source`:

```text
cli
```

### 20.5 Dokumentace CLI

Finální dokumentace aplikace musí obsahovat samostatnou kapitolu `CLI` s těmito informacemi:

- jak CLI spustit přes Docker Compose,
- seznam všech příkazů,
- příklady nejčastějších příkazů,
- popis potřebných environment variables,
- popis návratových kódů,
- postup vytvoření prvního Admin uživatele,
- postup založení partnera, klienta a uživatele partnera,
- postup ruční kontroly GitLab integrace.

## 21. Technický backlog MVP podle etap

### Etapa 0 - Příprava projektu a základní architektura

Cíl: připravit technické základy projektu tak, aby bylo možné implementovat MVP modulárně a bezpečně.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E0-01 | Založit repozitář a základní strukturu projektu | Backend, frontend, konfigurace, dokumentace | Projekt jde spustit v lokálním prostředí. |
| E0-02 | Navrhnout databázové schéma | První migrace DB | Migrace obsahuje základní entity pro User, Partner, Client, Ticket. |
| E0-03 | Připravit prostředí pro konfiguraci | Environment variables / config | Lze nastavit DB, SSO, SMTP, GitLab URL a GitLab token. |
| E0-04 | Připravit seed dat pro vývoj | Testovací role a uživatelé | Vývojář má testovací interní i externí účty. |
| E0-05 | Nastavit základní CI pipeline | Build/test pipeline | Pipeline ověří build a základní testy. |
| E0-06 | Připravit aplikační CLI skeleton | `ticketmaster-cli` v backend kontejneru | CLI jde spustit přes Docker Compose a má `--help`, `health`, `config check`, `db migrate`. |

### Etapa 1 - Autentizace, uživatelé a RBAC

Cíl: implementovat přihlášení, správu uživatelů, role a základní oprávnění.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E1-01 | Implementovat SSO pro interní uživatele | Login přes firemní identity provider | Interní uživatel se přihlásí přes SSO. |
| E1-02 | Implementovat e-mail + heslo pro externí uživatele | Lokální login | Partner user se přihlásí e-mailem a heslem. |
| E1-03 | Implementovat pozvánky e-mailem | Invite flow | Admin/DM pošle pozvánku, uživatel si nastaví heslo. |
| E1-04 | Implementovat role | Role model | Systém rozlišuje Odpovědnou osobu, Technickou osobu, DM, L1, L2, L3, Admin. |
| E1-05 | Implementovat základní RBAC middleware | Oprávnění | Neoprávněný uživatel se nedostane k zakázané akci. |
| E1-06 | Implementovat deaktivaci uživatele | User deactivation | Deaktivovaný uživatel se nepřihlásí, historie zůstává. |
| E1-07 | Doplnit CLI pro interní uživatele | CLI user commands | CLI umí vytvořit interního uživatele, přiřadit roli a deaktivovat uživatele. |

### Etapa 2 - Admin část: partneři, klienti, vazby

Cíl: umožnit interní správu partnerů, uživatelů a klientů.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E2-01 | CRUD partnerů | Admin UI + API | Admin vytvoří, upraví a deaktivuje partnera. |
| E2-02 | CRUD uživatelů partnera | Admin/DM UI + API | Admin/DM vytvoří partner usera a přiřadí mu roli. |
| E2-03 | CRUD klientů | Admin UI + API | Klient je vždy navázaný na partnera. |
| E2-04 | Vazba klient ↔ odpovědná osoba | ClientAssignment | Jeden klient může mít více odpovědných osob. |
| E2-05 | Validace převodu podle klienta | Business rule | Ticket s klientem lze převést jen na odpovědnou osobu s vazbou na klienta. |
| E2-06 | Doplnit CLI pro partnery, klienty a partner users | CLI admin commands | CLI umí vytvořit partnera, klienta, pozvat uživatele partnera a přiřadit odpovědnou osobu ke klientovi. |

### Etapa 3 - Partnerské tickety a partner dashboard

Cíl: umožnit odpovědné osobě partnera zakládat a sledovat tickety.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E3-01 | Formulář založení ticketu | Partner UI | Odpovědná osoba založí ticket s typem, prioritou, klientem/bez klienta, názvem a popisem. |
| E3-02 | Automatické vlastnictví ticketu | Ticket owner | Zakladatel se stane vlastníkem a účastníkem komunikace. |
| E3-03 | Přidání účastníků komunikace | Participant selector | Vybírat lze pouze uživatele stejného partnera. |
| E3-04 | Partner dashboard | Seznam ticketů partnera | Uživatel partnera vidí tickety svého partnera. |
| E3-05 | Detail ticketu pro partnera | Detail view | Partner vidí detail, komentáře, přílohy, historii a GitLab status. |
| E3-06 | Omezení komentování | Permission check | Komentovat může jen uživatel v komunikaci ticketu. |
| E3-07 | Vyhledávání a filtry | Partner filters | Filtry podle stavu, priority, typu, klienta, ID a názvu. |

### Etapa 4 - Interní workflow, fronty a řešení ticketů

Cíl: implementovat interní zpracování ticketu podle workflow a resolver týmů.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E4-01 | Interní dashboard | Internal UI | DM/Admin vidí vše, L1/L2/L3 jen svoji frontu a tickety svého oddělení. |
| E4-02 | Stavový automat ticketu | Status transitions | Systém povolí jen přechody definované v transition matrix. |
| E4-03 | Kontrola DM | Triage actions | DM může změnit typ, klienta, prioritu, vyžádat info, reject, duplicate, assign. |
| E4-04 | Resolver team | Assignment | Od Assigned je resolver_team povinný. |
| E4-05 | Assignee | Optional assignee | Ticket může být bez assignee nebo přiřazen konkrétnímu internímu uživateli. |
| E4-06 | Eskalace L1 -> L2 | Escalation | L1 může předat ticket na L2 bez DM. |
| E4-07 | Eskalace L2 -> L3 | Escalation | L2 může předat ticket na L3 bez DM. |
| E4-08 | Ruční uzavření ticketu | Close action | Resolved lze ručně uzavřít do Closed. |
| E4-09 | Zákaz mazání ticketů | No delete | Ticket nelze smazat, pouze ukončit stavem. |
| E4-10 | Doplnit CLI pro provozní úkony ticketů | CLI ticket commands | CLI umí zobrazit ticket, převést vlastníka, přiřadit resolver team, nastavit assignee a ručně uzavřít ticket. |

### Etapa 5 - Komunikace, přílohy, notifikace a audit

Cíl: doplnit provozní komunikaci, soubory, e-maily a historii změn.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E5-01 | Komentáře | Comment model + UI | Účastník komunikace může přidat komentář. |
| E5-02 | Interní poznámky | Internal note | Interní poznámka je viditelná pouze internímu týmu. |
| E5-03 | Soft delete komentářů | Comment moderation | DM/Admin smaže komentář soft delete způsobem. |
| E5-04 | Revize komentářů | CommentRevision | U úpravy/smazání je vidět kdo a kdy. |
| E5-05 | Přílohy | Attachment upload | Povolené typy a max 25 MB na soubor. |
| E5-06 | E-mailové notifikace | SMTP + šablony | Události z notifikační tabulky odesílají e-mail. |
| E5-07 | Watchers | TicketWatcher | Vlastník, účastníci a assignee jsou sledovatelé. |
| E5-08 | Audit log | Audit UI | Admin/DM vidí audit log v detailu ticketu. |

### Etapa 6 - GitLab integrace pro L3

Cíl: implementovat povinnou GitLab vazbu pro L3 tickety.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E6-01 | GitLab konfigurace | Admin/config | Lze nastavit GitLab URL, token a pevný projekt. |
| E6-02 | Automatické vytvoření issue | GitLab API integration | Při přiřazení na L3 vznikne GitLab issue. |
| E6-03 | Uložení GitLab vazby | GitLabLink | Ticket má max jedno hlavní GitLab issue. |
| E6-04 | Selhání vytvoření issue | Error state | Při chybě zůstane ticket Assigned/L3 a nepřejde do In progress. |
| E6-05 | GitLab status sync | GitLabIssueStatus | Systém načítá Open / To Do / In Progress / Done / Closed. |
| E6-06 | Viditelnost GitLab statusu | UI | Partner vidí GitLab status, ale ne GitLab link. |
| E6-07 | Audit GitLab událostí | GitLabSyncEvent | Vytvoření issue, sync i chyby jsou auditované. |
| E6-08 | Doplnit CLI pro GitLab integraci | CLI GitLab commands | CLI umí zkontrolovat GitLab konfiguraci, ručně vytvořit issue a ručně synchronizovat GitLab status. |

### Etapa 7 - Interní tickety

Cíl: implementovat jednoduché interní tickety v rámci MVP.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E7-01 | Založení interního ticketu | Internal ticket form | Interní ticket může založit DM, L1/L2/L3 nebo Admin. |
| E7-02 | Label Internal | Označení ticketu | V UI je jasně vidět, že jde o interní ticket. |
| E7-03 | Interní viditelnost | Permissions | Partner interní ticket nikdy nevidí. |
| E7-04 | Interní komentáře | Internal communication | Interní ticket má pouze interní komunikaci. |
| E7-05 | Stejné typy a workflow | Reuse | Interní ticket používá stejné typy a workflow jako partnerský ticket. |
| E7-06 | Doplnit CLI pro interní tickety | CLI internal ticket command | CLI umí založit jednoduchý interní ticket s typem, prioritou, názvem, popisem a volitelným resolver teamem. |

### Etapa 8 - Testování, bezpečnost a předání MVP

Cíl: ověřit, že systém odpovídá zadání a je připravený k pilotnímu provozu.

| ID | Úkol | Výstup | Akceptační kritéria |
|---|---|---|---|
| E8-01 | Unit testy business pravidel | Test suite | Testy pokrývají workflow, permissions, ownership, GitLab guard. |
| E8-02 | Integrační testy GitLab | Integration tests | Ověřeno vytvoření issue, sync stavu a chyba API. |
| E8-03 | E2E testy hlavních scénářů | E2E suite | Projde založení, triage, assign, comment, resolve, close. |
| E8-04 | Security test partner izolace | Security check | Partner A nikdy nevidí data partnera B. |
| E8-05 | Kontrola e-mailů | Notification QA | Události posílají e-maily správným příjemcům. |
| E8-06 | UAT scénáře | Předávací checklist | Uživatelé ověří scénáře podle akceptačních kritérií. |
| E8-07 | Dokumentace pro provoz | README/provozní dokumentace | Popsán deploy, konfigurace SSO, SMTP, GitLab, role a CLI. |
| E8-08 | Ověřit CLI v testech | CLI test checklist | Ověřeno spuštění CLI v Docker Compose, vytvoření admina, partnera, klienta, uživatele partnera a GitLab check. |

## 22. MVP akceptační kritéria

MVP je hotové, pokud platí všechny body níže:

1. Interní uživatel se přihlásí přes SSO.
2. Externí partner user se aktivuje přes e-mailovou pozvánku a přihlásí se e-mailem a heslem.
3. Admin/Delivery Manager umí spravovat partner usery.
4. Admin umí spravovat partnery, klienty a vazby klient ↔ odpovědná osoba.
5. Odpovědná osoba partnera založí ticket.
6. Technická osoba partnera ticket nezaloží.
7. Uživatelé partnera vidí jen tickety svého partnera.
8. Uživatel partnera komentuje jen ticket, kde je v komunikaci.
9. Delivery Manager umí provést triage a přiřadit ticket na L1/L2/L3.
10. L1 vidí jen L1 frontu a tickety řešené L1.
11. L2 vidí jen L2 frontu a tickety řešené L2.
12. L3 vidí jen L3 frontu a tickety řešené L3.
13. L1 umí eskalovat na L2.
14. L2 umí eskalovat na L3.
15. L3 ticket automaticky vytvoří GitLab issue.
16. L3 ticket nesmí přejít do In progress bez GitLab issue nebo vědomého překlenutí chyby.
17. GitLab status je viditelný partnerovi.
18. GitLab link je viditelný jen internímu týmu.
19. E-mailové notifikace fungují pro definované události.
20. Audit log je viditelný pro Admina a Delivery Managera.
21. Interní ticket je viditelný pouze interně.
22. Ticket nelze smazat.
23. Reopen není dostupný.
24. Automatické uzavírání není dostupné.
25. Aplikační CLI je dostupné jako binárka v backend Docker kontejneru.
26. CLI umí vytvořit interního uživatele, partnera, klienta, uživatele partnera a provést základní diagnostiku.
27. CLI příkazy měnící aplikační data zapisují audit se zdrojem `cli`.

## 23. Rizika a body ke kontrole při vývoji

| Riziko | Dopad | Opatření |
|---|---|---|
| Špatná izolace partnerů | Únik dat mezi partnery | Testovat tenant izolaci na úrovni API i UI. |
| L1/L2/L3 uvidí více ticketů, než mají | Interní informační šum / riziko přístupu | Implementovat scoped queries podle resolver_team a assignee. |
| GitLab status bude zaměněn za ticket status | Zmatek v procesu | UI musí jasně oddělit Ticket status a GitLab status. |
| GitLab issue se nevytvoří | L3 ticket se zasekne | Implementovat chybový stav, audit a blokaci In progress. |
| Delivery Manager bude zahlcen notifikacemi | Nízká použitelnost | Po assignu posílat DM jen relevantní notifikace. |
| Převod vlastnictví na špatného uživatele | Špatná odpovědnost za ticket | Validovat partnera i vazbu na klienta. |
| Interní ticket se zobrazí partnerovi | Únik interních informací | Interní tickety musí mít oddělenou permission kontrolu. |
| CLI obejde business pravidla aplikace | Nekonzistentní data / bezpečnostní riziko | CLI musí používat stejné validační služby jako backend a zapisovat audit. |

## 24. Doporučená struktura předání vývojářům

Vývojářům předat:

- tento dokument jako hlavní zadání,
- GitLab projekt / URL / token až při implementaci integrace,
- seznam interních testovacích uživatelů,
- seznam testovacích partnerů a klientů,
- SMTP konfiguraci,
- SSO konfiguraci,
- rozhodnutí o finálním formátu Ticket ID,
- finální provozní dokumentaci včetně CLI příkazů a Docker Compose postupů.

## 25. Závěr

TicketMaster MVP má být jednoduchý, procesně přesný a bezpečný systém pro práci s partnerskými a interními tickety.

Nejdůležitější pravidla:

- partner vidí pouze svoje tickety,
- komentování je řízené komunikací ticketu,
- Delivery Manager řídí vstupní posouzení,
- L1/L2/L3 řeší vlastní fronty,
- L3 vyžaduje GitLab issue,
- GitLab status vidí i partner,
- GitLab link zůstává interní,
- interní tickety nevidí žádný partner,
- ticket se nemaže,
- audit je povinný,
- aplikace má mít CLI dostupné přes Docker kontejner pro bootstrap a základní administraci.
