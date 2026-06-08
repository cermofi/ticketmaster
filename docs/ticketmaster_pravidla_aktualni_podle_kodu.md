# TicketMaster - aktualni pravidla podle kodu

Tento dokument popisuje aktualni chovani aplikace TicketMaster podle soucasneho kodu backendu, UI a API.

Nejde o navrh budoucich funkci ani implementacni zadani. Pokud se nekde kod a puvodni dokumentace rozchazi, ma prednost tento dokument jako popis aktualniho stavu.

> WebUI aplikace ma byt postavena nad TeskaLabs ASAB WebUI ekosystemem. Konkretne ma vychazet z `asab-webui` a `asab-webui-shell-lib`. Dokument dale neresi konkretni UI navrh, layouty ani implementacni detaily frontendu.

## 1. Zakladni model produktu

TicketMaster je system pro spravu ticketu mezi internimi tymy a partnery.

Hlavni principy:

- interni uzivatele resi ticket uvnitr organizace,
- partneri zakladaji a sleduji vlastni tickety,
- ticket ma vlastnika, resolver team, pripadne assignee,
- partneri vidi pouze sve tickety,
- interni role vidi ticket podle pravidel viditelnosti,
- komunikace probiha pres komentare a internal notes,
- L3 workflow je navazane na GitLab issue,
- ticket se po uzavreni uzamkne pro dalsi komunikaci a assignment.

## 2. Role a ucty

### 2.1 Interni role

Interni uzivatele maji jednu z nasledujicich roli:

- `Admin`
- `DeliveryManager`
- `L1`
- `L2`
- `L3`

### 2.2 Partner role

Partner uzivatele maji jednu z nasledujicich roli:

- `responsible`
- `technical`

### 2.3 Stav uctu

Aktivni/neaktivni stav existuje pouze u uzivatelu.

U partneru a klientu se `active` stav v aktualnim modelu nepouziva.

Pravidla pro uzivatele:

- neaktivni uzivatel se nemuze prihlasit,
- neaktivni uzivatel nemuze vytvaret tickety,
- neaktivni uzivatel nemuze pridavat komentare ani internal notes,
- neaktivni uzivatel je vynucen na backendu, ne jen v UI.

## 3. Prihlaseni a autentizace

### 3.1 Interni uzivatele

Interni uzivatel se prihlasuje pres interni autentizacni flow podle deploymentu. V kodu je oddeleny od partner prihlaseni.

### 3.2 Partner uzivatele

Partner uzivatele se prihlasuji e-mailem a heslem.

### 3.3 Aktivace a reset hesla

System podporuje:

- pozvanku partner uzivatele,
- nastaveni hesla pri aktivaci uctu,
- reset hesla pres token / invitation flow.

### 3.4 Chyba pri neprihlasenem nebo neaktivnim uzivateli

Pri pokusu o prihlaseni neaktivniho uzivatele vraci backend chybu ve smyslu, ze ucet neni aktivni.

## 4. Partneri a klienti

### 4.1 Partner

Partner je nadrizena entita pro skupinu uzivatelu a klientu.

Aktualni model partnera obsahuje pouze:

- `id`
- `key`
- `name`
- `created_at`

Partner nema `active/inactive` stav.

### 4.2 Client

Client patri do jednoho partnera.

Aktualni model klienta obsahuje pouze:

- `id`
- `key`
- `partner_id`
- `name`
- `created_at`

Client nema `active/inactive` stav.

### 4.3 Vazby

Platilo a plati:

- klient patri k jednomu partnerovi,
- partneri maji vlastni uzivatele,
- ticket musi zustat v systemu i tehdy, kdyz se meni nebo rusit vazby okolo partnera nebo klienta,
- ticket se nikdy nema hard delete.

### 4.4 Smazani partnera a klienta

Aktualni kod ma delete endpointy i validacni pravidla kolem mazani partneru a klientu.

V soucasnem stavu je potreba pocitat s tim, ze:

- partner/klient uz nemaji `active` stav,
- mazani je vazano na backend validace,
- pokud je treba definitivne povolit nebo zakazat hard delete, je to samostatny pravidlovy bod, ktery musi byt konzistentne vyresen v API i UI.

## 5. Viditelnost ticketu

Ticket je viditelny podle teto logiky:

- `Admin` vidi vse,
- `DeliveryManager` vidi vse,
- `L1`, `L2`, `L3` vidi ticket, pokud:
  - patri do jejich resolver teamu, nebo
  - jsou jeho assignee, nebo
  - je ticket jejich vlastni v ramci povolene logiky,
- partner uzivatel vidi jen ticket svyho partnera a jen pokud ticket neni interni.

### 5.1 Interni vs partner ticket

- `internal = true` znamena interny ticket bez partnera a klienta,
- partner ticket ma vazbu na partnera a muze mit i klienta,
- partner uzivatel nevidi interni tickety.

## 6. Vlastnictvi ticketu

### 6.1 Owner

Ticket ma jednoho ownera.

U partner ticketu je owner odpovedna osoba partnera.

Pri zalozeni ticketu:

- owner je zalozeny uzivatel, ktery ticket vytvoril,
- owner se automaticky stava participantem a watcherem,
- owner muze ridit komunikaci a participanty v rozsahu opravneni.

### 6.2 Transfer owner

Owner lze prevest na jineho partner uzivatele s rolí `responsible` ve stejnem partnerovi.

Pokud je ticket navazany na klienta, novy owner musi byt zaroven odpovednou osobou tohoto klienta.

## 7. Ticket typy a priority

### 7.1 Typy ticketu

Podporovane typy v kodu:

- `Problem`
- `Change Request`
- `New Feature`
- `Question`
- `Configuration`
- `Integration`
- `Security Issue`
- `Operational Request`

### 7.2 Priority

Podporovane priority:

- `Low`
- `Normal`
- `High`
- `Critical`

### 7.3 Specialni pravidlo pro Security Issue

Pro `Security Issue` muze backend automaticky povysit prioritu `Normal` na `Critical`.

## 8. Workflow ticketu

### 8.1 Statusy

Aktualni statusy ticketu:

- `New`
- `Need more info`
- `Assigned`
- `In progress`
- `Resolved`
- `Closed`
- `Rejected`
- `Duplicate`
- `Cancelled`

### 8.2 Povolené prechody

Povolené prechody v kodu:

- `New` -> `Need more info`
- `New` -> `Assigned`
- `New` -> `Rejected`
- `New` -> `Duplicate`
- `New` -> `Cancelled`
- `Need more info` -> `Assigned`
- `Need more info` -> `Rejected`
- `Need more info` -> `Cancelled`
- `Assigned` -> `In progress`
- `Assigned` -> `Need more info`
- `Assigned` -> `Cancelled`
- `In progress` -> `Resolved`
- `In progress` -> `Need more info`
- `In progress` -> `Assigned`
- `Resolved` -> `Closed`
- `Rejected` -> `Closed`
- `Duplicate` -> `Closed`
- `Cancelled` -> `Closed`

`Closed` je finalni stav bez dalsiho prechodu.

### 8.3 Kdo muze menit workflow

- `Admin` a `DeliveryManager` mohou provadet povolene workflow prechody,
- `L1`, `L2`, `L3` mohou provadet pouze povolene prechody nad tiketem, ktery patri do jejich resolver teamu,
- partner uzivatel v aktualni implementaci workflow stav ticketu menit nemuze.

### 8.4 Need more info

`Need more info` je bezny workflow stav.

V kodu se pouziva jako:

- mezistav pri cekani na doplneni informaci,
- stav, do ktereho se ticket muze vratit z `Assigned` nebo `In progress`,
- stav, ze ktereho je mozne dal pokracovat na `Assigned`, `Rejected` nebo `Cancelled` podle opravneni.

### 8.5 Uzavreny ticket

U uzavreneho ticketu:

- nelze pridavat komentare,
- nelze pridavat internal notes,
- nelze ticket assignovat,
- nelze menit workflow.

## 9. Resolver team a assignee

### 9.1 Resolver team

Resolver team je jedna z hodnot:

- `L1`
- `L2`
- `L3`

Ticket muze byt prirazeny do resolver teamu.

### 9.2 Assignee

Assignee je konkreti interni uzivatel patrii do resolver teamu ticketu.

Pravidla:

- assignee musi byt aktivni interni uzivatel,
- assignee musi patrit do stejneho resolver teamu jako ticket,
- resolver team se po nastaveni nemeni na jiny tym,
- meni se jen assignee v ramci stejneho tymu,
- tiket lze vratit do fronty bez assignee, ale bez zmeny tymu.

### 9.3 Prirazeni ticketu

Ticket lze prirazovat podle pravidel backendu:

- `Admin` a `DeliveryManager` mohou prirazovat libovolne v ramci podporovanych resolver teamu,
- resolver role mohou prirazovat jen v ramci sveho povoleneho toku,
- ticket bez resolver teamu se po prirazeni presune do stavu `Assigned`.

## 10. Escalation a dalsi pohyb ticketu

### 10.1 Eskalace mezi tymy

Aktualni pravidlo je, ze ticket po prirazeni do resolver teamu nema prechazet mezi oddelenimi.

Prace se deje takto:

- ticket vstoupi do resolver teamu,
- v ramci toho tymu se meni assignee,
- tym se uz nemente na jiny tym.

### 10.2 Unassign / vratit do fronty

Ticket lze vratit z konkretniho assignee zpet do fronty stejneho resolver teamu.

To znamena:

- assignee se smaze,
- resolver team zustava zachovan,
- ticket se vrati do stavu odpovidajiciho fronty,
- nedochazi ke zmene oddeleni.

## 11. Partnersky dashboard

Partnersky dashboard ma slouzit partner uzivateli.

Aktualni data na dashboardu mohou obsahovat:

- prehled klientu partnera,
- seznam odpovednych osob u klientu,
- samostatny seznam technickych osob partnera.

Technicka osoba nema v systemu samostatneho klienta, je vedena jako partner uzivatel bez klientske vazby.

## 12. Komunikace v ticketu

### 12.1 Komentare

Komentare jsou verejna komunikace viditelna podle opravneni k ticketu.

Pravidla:

- partner uzivatel muze komentovat jen pokud je participantem ticketu,
- interni uzivatel muze komentovat ticket, ktery vidi,
- komentar na `Closed` ticketu neni povolen.

### 12.2 Internal notes

Internal notes jsou viditelne jen internimu tymu.

Pravidla:

- partner je nevidi,
- na `Closed` ticketu je nelze pridat,
- jsou dostupne jen internim uzivatelum s opravnenim k ticketu.

### 12.3 Editace a mazani komentaru

V aktualni implementaci je editace a mazani komentaru i internal notes vypnute.

To znamena:

- UI nema nabizet edit ani delete akce,
- API je ma vratit jako nedostupne.

## 13. GitLab integrace

GitLab integrace je v kodu navazana na L3 workflow.

### 13.1 Kdy se GitLab issue vytvari

GitLab issue se muze vytvorit:

- pri assignu ticketu na `L3`,
- pri vytvoreni internal ticketu s resolver teamem `L3`,
- manualne pres interni akci nebo API,
- pres CLI.

### 13.2 Co je viditelne komu

- interni uzivatel vidi GitLab link i status,
- partner uzivatel vidi GitLab status jako doplnkovou informaci,
- samotny GitLab odkaz je interni.

### 13.3 Guard pro L3

Pokud je ticket v `L3` a ma prejit do `In progress`, backend kontroluje existenci GitLab issue.

Pokud issue chybi, prechod se zablokuje.

### 13.4 Stav GitLabu

V kodu se pracuje s GitLab status hodnotami:

- `Open`
- `To Do`
- `In Progress`
- `Done`
- `Closed`

## 14. Administrace a sprava dat

### 14.1 Partneri

Partneri jsou spravovani z admin casti.

V UI a API se muze objevit delete akce, ale aktualni backend pravidla mohou mazani blokovat podle vazeb.

### 14.2 Klienti

Klienti jsou spravovani v navaznosti na partnera.

Klient nesmi zustat bez partnera.

### 14.3 Uzivatele

Uzivatele lze deaktivovat.

Pravidla:

- uzivatel nemuze deaktivovat sam sebe,
- nelze odebrat posledniho aktivniho Admina,
- po deaktivaci uzivatele se zablokuje dalsi cinnost podle auth a permission vrstvy.

## 15. Otevrene body

Tyto body jsou v kodu nebo v prevzatem zadani misty jeste nejednoznacne a je dobre je drzet explicitne:

1. Presny finalni zpusob mazani partneru a klientu vs. backend validace.
2. Presny text chyb pri neaktivnim uctu a pri nepovolene operaci.
3. Zda ma mit klient nekdy vlastni UI stav mimo vazby na partnera.
4. Zda se ma do budoucna rozsirit partner dashboard o dalsi agregace.

## 16. Strucne shrnuti aktualniho stavu

- Partner a klient uz nemaji `active/inactive` stav.
- `active/inactive` zustava jen u uzivatelu.
- Neaktivni uzivatel se neprihlasi a nic neprovede.
- Ticket se nikdy nema odstranit z historie systemu.
- Komentare a internal notes se needituji ani nemazou.
- Resolver team se po prirazeni nema prepinat mezi oddeleními.
- Menit lze hlavne assignee v ramci stejneho tymu.
- GitLab je navazany na L3 workflow.
- Partner vidi jen sve ticketove prostredi, ne interni komunikaci.
