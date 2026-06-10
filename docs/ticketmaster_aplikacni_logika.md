# TicketMaster - aplikacni logika

Tento dokument popisuje funkcni pravidla aplikace TicketMaster. Je urceny jako predavaci specifikace pro vyvojare, kteri maji podle pravidel postavit hotovou aplikaci.

## 1. Ucel aplikace

TicketMaster je aplikace pro evidenci, predavani a reseni ticketu mezi partnery a internimi resitelskymi tymy.

Aplikace podporuje dva hlavni typy ticketu:

- partnersky ticket, ktery zaklada partner,
- interni ticket, ktery zaklada interni uzivatel.

Partner vidi jen vlastni partnerske tickety. Interni tym pracuje s tickety podle roli, resolver teamu a prirazeni.

Ticket je hlavni historicky zaznam aplikace. Ticket se nesmi ztratit ani byt odstranen z evidence.

## 2. Uzivatele a role

### 2.1 Typy uzivatelu

Uzivatel je bud:

- interni uzivatel,
- partner uzivatel.

Interni uzivatel patri do interni organizace.

Partner uzivatel patri prave k jednomu partnerovi.

### 2.2 Interni role

Interni role jsou:

- `Admin`
- `DeliveryManager`
- `L1`
- `L2`
- `L3`

### 2.3 Partner role

Partner role jsou:

- `responsible`
- `technical`

`responsible` znamena odpovedna osoba partnera.

`technical` znamena technicka osoba partnera.

### 2.4 Aktivni a neaktivni ucet

Stav aktivni/neaktivni existuje pouze u uzivatelu.

Partner a klient nemaji stav aktivni/neaktivni.

Neaktivni uzivatel:

- se nemuze prihlasit,
- nemuze zalozit ticket,
- nemuze pridat komentar,
- nemuze pridat interni poznamku,
- nema provadet zadnou aktivni cinnost v aplikaci.

Pri prihlaseni neaktivniho uzivatele aplikace vraci chybu, ze ucet neni aktivni.

### 2.5 Ochrana Admin uctu

Aplikace musi chranit posledni aktivni `Admin` ucet.

Nelze:

- deaktivovat posledniho aktivniho Admina,
- zmenit roli posledniho aktivniho Admina tak, aby v aplikaci nezustal zadny aktivni Admin.

Uzivatel nesmi deaktivovat sam sebe.

## 3. Prihlaseni a aktivace uctu

### 3.1 Interni uzivatele

Interni uzivatel se prihlasuje internim prihlasovacim tokem.

Interni uzivatel musi byt predem zalozeny v aplikaci.

### 3.2 Partner uzivatele

Partner uzivatel se prihlasuje e-mailem a heslem.

Partner uzivatel vznikne pozvankou.

Pozvanka obsahuje aktivacni token, pomoci ktereho si uzivatel nastavi heslo.

Heslo musi mit alespon 8 znaku.

### 3.3 Reset hesla

Reset hesla vytvori novy token pro nastaveni hesla.

Reset hesla lze poslat pouze aktivnimu uzivateli.

U interniho uzivatele smi reset hesla vyvolat pouze `Admin`.

## 4. Partneri

Partner reprezentuje organizaci nebo skupinu, pod kterou patri partner uzivatele a klienti.

Partner ma:

- identifikator,
- unikatni klic,
- nazev,
- datum vytvoreni.

Partner nema stav aktivni/neaktivni.

Partnera smi zalozit pouze `Admin`.

Partnera nelze odstranit.

Partneri jsou viditelni pro `Admin` a `DeliveryManager`.

Partner uzivatel nevidi seznam partneru.

## 5. Klienti

Klient je subjekt nebo system v ramci partnera.

Klient patri prave k jednomu partnerovi.

Klient ma:

- identifikator,
- unikatni klic,
- partnera,
- nazev,
- datum vytvoreni.

Klient nema stav aktivni/neaktivni.

Klienta smi zalozit `Admin` nebo `DeliveryManager`.

Klienta smi prejmenovat `Admin` nebo `DeliveryManager`.

Klienta nelze odstranit.

Partner uzivatel vidi klienty sveho partnera.

Interni uzivatele s roli `Admin` nebo `DeliveryManager` vidi klienty napric partnery a mohou je filtrovat podle partnera.

## 6. Vazba klienta a odpovedne osoby

Klient muze mit prirazene odpovedne osoby.

Odpovedna osoba klienta musi splnovat vsechny podminky:

- je aktivni,
- je partner uzivatel,
- ma roli `responsible`,
- patri ke stejnemu partnerovi jako klient.

Vazbu odpovedne osoby ke klientovi smi vytvorit `Admin` nebo `DeliveryManager`.

Vazbu odpovedne osoby ke klientovi smi odebrat `Admin` nebo `DeliveryManager`.

Jedna odpovedna osoba muze byt prirazena k vice klientum.

Jeden klient muze mit vice odpovednych osob.

## 7. Sprava uzivatelu

### 7.1 Interni uzivatele

Interniho uzivatele smi vytvorit pouze `Admin`.

Pri vytvoreni interniho uzivatele se nastavuje:

- e-mail,
- jmeno,
- interni role.

Interni uzivatel je po vytvoreni aktivni.

Interniho uzivatele smi upravovat pouze `Admin`.

### 7.2 Partner uzivatele

Partner uzivatele smi vytvorit `Admin` nebo `DeliveryManager`.

Partner uzivatel se vytvari pozvankou.

Pri vytvoreni partner uzivatele se nastavuje:

- partner,
- e-mail,
- jmeno,
- partner role.

Partner uzivatel je po vytvoreni aktivni.

Partner uzivatele smi upravovat `Admin` nebo `DeliveryManager`.

### 7.3 Uprava uzivatele

U uzivatele lze upravit:

- e-mail,
- jmeno,
- roli,
- aktivni/neaktivni stav.

E-mail musi byt unikatni.

Role musi odpovidat typu uzivatele.

Internimu uzivateli lze nastavit pouze interni roli.

Partner uzivateli lze nastavit pouze partner roli.

### 7.4 Odstraneni uzivatele

Odstraneni uzivatele znamena deaktivaci uctu.

Zaznam uzivatele zustava v aplikaci kvuli historii ticketu, komentaru, auditu a vazeb.

## 8. Ticket

Ticket je hlavni pracovni jednotka aplikace.

Ticket ma:

- identifikator,
- priznak, zda je interni,
- partnera, pokud jde o partnersky ticket,
- klienta, pokud je ticket navazan na klienta,
- vlastnika,
- autora,
- typ,
- prioritu,
- stav,
- resolver team,
- assignee,
- nazev,
- popis,
- datum vytvoreni,
- datum posledni zmeny.

Ticket se neodstranuje.

Ticket muze byt:

- bez resolver teamu,
- ve fronte konkretniho resolver teamu,
- prirazeny konkretnimu assignee.

## 9. Typy ticketu

Povolene typy ticketu jsou:

- `Problem`
- `Change Request`
- `New Feature`
- `Question`
- `Configuration`
- `Integration`
- `Security Issue`
- `Operational Request`

Typ ticketu musi byt jedna z povolenych hodnot.

## 10. Priority ticketu

Povolene priority jsou:

- `Low`
- `Normal`
- `High`
- `Critical`

Priorita musi byt jedna z povolenych hodnot.

Pokud je typ ticketu `Security Issue` a uzivatel zvoli prioritu `Normal`, aplikace nastavi prioritu `Critical`.

## 11. Statusy ticketu

Povolene statusy ticketu jsou:

- `New`
- `Need more info`
- `Assigned`
- `In progress`
- `Resolved`
- `Closed`
- `Rejected`
- `Duplicate`
- `Cancelled`

`Closed` je konecny stav.

## 12. Vytvoreni partnerskeho ticketu

Partnersky ticket smi vytvorit pouze aktivni partner uzivatel s roli `responsible`.

Partner uzivatel s roli `technical` ticket vytvorit nesmi.

Partnersky ticket se zaklada pod partnerem uzivatele, ktery ho vytvari.

Pri zalozeni partnerskeho ticketu se nastavuje:

- typ,
- priorita,
- nazev,
- popis,
- volitelny klient,
- volitelni participanti.

Pokud je vybran klient:

- klient musi patrit ke stejnemu partnerovi jako zakladajici uzivatel,
- zakladajici uzivatel musi byt odpovednou osobou vybraneho klienta.

Po zalozeni partnerskeho ticketu plati:

- ticket ma stav `New`,
- vlastnikem je zakladajici odpovedna osoba,
- autorem je zakladajici odpovedna osoba,
- ticket neni interni,
- vlastnik se automaticky stava participantem,
- vlastnik se automaticky stava watcherem,
- volitelni participanti musi byt aktivni uzivatele stejneho partnera,
- Delivery Manageri dostanou informaci o novem ticketu.

## 13. Vytvoreni interniho ticketu

Interni ticket smi vytvorit aktivni interni uzivatel s roli:

- `Admin`
- `DeliveryManager`
- `L1`
- `L2`
- `L3`

Pri zalozeni interniho ticketu se nastavuje:

- typ,
- priorita,
- nazev,
- popis,
- volitelny resolver team.

Po zalozeni interniho ticketu plati:

- ticket je interni,
- nema partnera,
- nema klienta,
- vlastnikem je zakladajici interni uzivatel,
- autorem je zakladajici interni uzivatel,
- zakladajici uzivatel se automaticky stava watcherem.

Pokud je pri zalozeni vybran resolver team:

- ticket zacina ve stavu `Assigned`,
- resolver team je nastaven na vybranou hodnotu.

Pokud resolver team vybran neni:

- ticket zacina ve stavu `New`,
- resolver team neni nastaven.

Pokud je interni ticket zalozen rovnou pro `L3`, aplikace se pokusi zalozit hlavni GitLab issue.

## 14. Viditelnost ticketu

### 14.1 Admin a Delivery Manager

`Admin` a `DeliveryManager` vidi vsechny tickety.

### 14.2 Resolver role L1, L2, L3

Uzivatel s roli `L1`, `L2` nebo `L3` vidi ticket, pokud plati alespon jedna podminka:

- ticket ma resolver team stejny jako role uzivatele,
- ticket je prirazen primo tomuto uzivateli,
- uzivatel je vlastnikem ticketu.

### 14.3 Partner uzivatele

Partner uzivatel vidi partnerske tickety sveho partnera.

Partner uzivatel nevidi interni tickety.

Partner uzivatel nevidi tickety jinych partneru.

Viditelnost ticketu partner uzivatelem neznamena automaticky pravo komentovat.

## 15. Vyhledavani a filtrovani ticketu

Seznam ticketu zobrazuje pouze tickety viditelne pro prihlaseneho uzivatele.

Tickety se radi od nejnovejsich.

Seznam ticketu lze filtrovat podle:

- textoveho hledani,
- statusu,
- priority,
- typu,
- resolver teamu,
- partnera,
- toho, zda je ticket interni.

Textove hledani pracuje s:

- identifikatorem ticketu,
- nazvem ticketu,
- popisem ticketu,
- verejnymi komentari.

## 16. Workflow ticketu

### 16.1 Povolene prechody

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
| `Closed` | zadny dalsi prechod |

### 16.2 Kdo muze menit status

Partner uzivatele status ticketu nemeni.

`Admin` a `DeliveryManager` mohou provadet povolene workflow prechody u vsech ticketu.

Uzivatel s roli `L1`, `L2` nebo `L3` muze menit status jen u ticketu sveho resolver teamu.

Resolver role mohou pouzit tyto cilove statusy:

- `In progress`
- `Resolved`
- `Need more info`
- `Assigned`
- `Closed`

Prechod do ciloveho statusu musi byt zaroven povolen workflow tabulkou.

### 16.3 Dostupne dalsi stavy

Aplikace ma uzivateli nabizet pouze takove dalsi stavy ticketu, ktere:

- jsou povolene workflow tabulkou,
- odpovidaji roli uzivatele,
- splnuji vsechny business podminky ticketu.

Zakazane prechody se uzivateli nemaji nabizet jako volba.

## 17. Need more info

`Need more info` znamena, ze ticket ceka na doplneni informaci.

Do stavu `Need more info` lze prejit:

- z `New`,
- z `Assigned`,
- z `In progress`.

Ze stavu `Need more info` lze pokracovat:

- na `Assigned`,
- na `Rejected`,
- na `Cancelled`.

## 18. Uzavreny ticket

Ticket ve stavu `Closed` je uzavreny.

U uzavreneho ticketu:

- nelze pridat komentar,
- nelze pridat interni poznamku,
- nelze nahrat prilohu, protoze prilohu smi nahrat jen uzivatel s pravem komentovat,
- nelze provest assign,
- nelze provest unassign,
- nelze provest dalsi workflow prechod.

Partner uzivatel nesmi ticket uzavrit.

`Admin` a `DeliveryManager` mohou ticket uzavrit i mimo bezny terminalni stav.

Resolver role mohou ticket uzavrit pouze tehdy, kdyz jim to povoli workflow a opravneni.

## 19. Resolver team a assignee

### 19.1 Resolver team

Resolver team je jedna z hodnot:

- `L1`
- `L2`
- `L3`

Resolver team urcuje oddeleni, ktere ticket resi.

Jakmile je resolver team nastaven, ticket nesmi prejit do jineho resolver teamu.

### 19.2 Assignee

Assignee je konkretni interni uzivatel prirazeny k ticketu.

Assignee musi byt interni uzivatel ze stejneho resolver teamu jako ticket.

Assignee se muze menit v ramci stejneho resolver teamu.

### 19.3 Assign

Assign nastavuje:

- resolver team,
- volitelne assignee,
- stav ticketu na `Assigned`.

Assign nelze provest u ticketu ve stavu `Closed`.

`Admin` a `DeliveryManager` mohou assignovat ticket do libovolneho povoleneho resolver teamu, pokud tim nedojde ke zmene uz nastaveneho resolver teamu.

Resolver role muze assignovat pouze ticket, ktery uz patri do jejiho resolver teamu, a pouze zpet do stejneho resolver teamu.

Pokud je ticket assignovan na `L3`, aplikace se pokusi zalozit hlavni GitLab issue.

### 19.4 Unassign

Unassign vraci ticket z konkretniho assignee zpet do fronty stejneho resolver teamu.

Unassign:

- smi provest pouze `Admin` nebo `DeliveryManager`,
- nelze provest u ticketu ve stavu `Closed`,
- vyzaduje, aby ticket mel resolver team,
- nastavi assignee na prazdnou hodnotu,
- zachova resolver team,
- nastavi stav ticketu na `Assigned`.

## 20. Vlastnik ticketu

### 20.1 Vlastnik partnerskeho ticketu

Vlastnikem partnerskeho ticketu je odpovedna osoba partnera.

Vlastnik:

- je hlavni odpovedna osoba za ticket na strane partnera,
- je automaticky participant,
- je automaticky watcher,
- nemuze byt odebran z participantu.

### 20.2 Vlastnik interniho ticketu

Vlastnikem interniho ticketu je interni uzivatel, ktery ticket zalozil.

Interni ticket nema partner ownera.

### 20.3 Prevod vlastnictvi

Vlastnictvi lze prevadet pouze u partnerskeho ticketu.

Prevod vlastnictvi smi provest:

- `Admin`,
- `DeliveryManager`,
- stavajici vlastnik ticketu.

Novy vlastnik musi splnovat vsechny podminky:

- je partner uzivatel,
- ma roli `responsible`,
- patri ke stejnemu partnerovi jako ticket.

Pokud ma ticket klienta, novy vlastnik musi byt odpovednou osobou tohoto klienta.

Novy vlastnik se automaticky stava participantem a watcherem.

## 21. Participanti a watcheri

### 21.1 Participant

Participant je partner uzivatel zapojeny do komunikace partnerskeho ticketu.

Participant muze pridavat verejne komentare, pokud muze ticket videt a ticket neni uzavreny.

Participanty lze spravovat pouze u partnerskeho ticketu.

Spravu participantu smi provest:

- vlastnik ticketu,
- `Admin`,
- `DeliveryManager`.

Participant musi byt uzivatel stejneho partnera jako ticket.

Vlastnika ticketu nelze odebrat z participantu.

### 21.2 Watcher

Watcher je uzivatel, ktery dostava informace o udalostech ticketu.

Participant se automaticky stava watcherem.

Assignee se automaticky stava watcherem.

Zakladajici uzivatel interniho ticketu se automaticky stava watcherem.

## 22. Komunikace

### 22.1 Verejny komentar

Verejny komentar vidi interni uzivatele s pravem videt ticket a partner uzivatele podle viditelnosti ticketu.

Komentar smi pridat:

- aktivni interni uzivatel, ktery ticket vidi,
- aktivni partner uzivatel, ktery je participantem ticketu.

Komentar nelze pridat u ticketu ve stavu `Closed`.

### 22.2 Interni poznamka

Interni poznamku vidi pouze interni uzivatele.

Interni poznamku smi pridat aktivni interni uzivatel, ktery ticket vidi.

Partner uzivatel interni poznamku nevidi.

Interni poznamku nelze pridat u ticketu ve stavu `Closed`.

### 22.3 Editace a mazani komunikace

Komentare a interni poznamky se v aplikaci needituji.

Komentare a interni poznamky se v aplikaci nemazou.

## 23. Prilohy

Prilohu lze nahrat pouze k ticketu, ke kteremu ma uzivatel pravo pridat komentar.

To znamena:

- uzivatel musi ticket videt,
- uzivatel musi byt opravnen komentovat,
- ticket nesmi byt ve stavu `Closed`.

Povolene typy priloh jsou:

- `.png`
- `.jpg`
- `.jpeg`
- `.pdf`
- `.txt`
- `.log`
- `.zip`

Maximalni velikost prilohy je 25 MB.

Prilohu muze stahnout uzivatel, ktery vidi ticket.

## 24. GitLab logika

GitLab je navazany na reseni ticketu v teamu `L3`.

### 24.1 Hlavni GitLab issue

Ticket muze mit hlavni GitLab issue.

Aplikace se pokusi zalozit hlavni GitLab issue:

- pri assignu ticketu na `L3`,
- pri vytvoreni interniho ticketu s resolver teamem `L3`.

Interni uzivatel muze zalozit GitLab issue rucne.

Partner uzivatel GitLab issue nezaklada.

Pokud hlavni GitLab issue uz existuje, aplikace pouzije existujici vazbu.

### 24.2 GitLab status

GitLab status muze byt:

- `Open`
- `To Do`
- `In Progress`
- `Done`
- `Closed`

Partner muze videt GitLab status jako doplnkovou informaci.

GitLab odkaz je viditelny pouze internim uzivatelum.

### 24.3 Guard pro L3 praci

Ticket v resolver teamu `L3` nesmi prejit do stavu `In progress`, pokud nema hlavni GitLab issue.

Vyjimkou je pripad, kdy je u ticketu explicitne povolene prepsani GitLab chyby.

### 24.4 Synchronizace GitLab statusu

GitLab status smi synchronizovat pouze interni uzivatel.

Pokud GitLab issue neexistuje, synchronizace neni mozna.

## 25. Partner dashboard

Partner dashboard je dostupny pouze partner uzivateli.

Partner dashboard zobrazuje:

- klienty partnera,
- odpovedne osoby u jednotlivych klientu,
- informaci, zda je prihlaseny uzivatel odpovednou osobou daneho klienta,
- technicke osoby partnera.

Technicke osoby jsou vedeny jako samostatny seznam partner uzivatelu s roli `technical`.

Technicka osoba nema primou vazbu na klienta pres odpovednost za klienta.

## 26. Audit

Aplikace eviduje dulezite zmeny jako auditni udalosti.

Auditni udalosti vznikaji zejmena pri:

- prihlaseni,
- neuspesnem prihlaseni,
- aktivaci uctu,
- vytvoreni uzivatele,
- uprave uzivatele,
- deaktivaci uzivatele,
- vytvoreni partnera,
- vytvoreni klienta,
- uprave klienta,
- prirazeni odpovedne osoby ke klientovi,
- odebrani odpovedne osoby od klienta,
- vytvoreni ticketu,
- zmene stavu ticketu,
- assignu,
- unassignu,
- prevodu vlastnictvi,
- sprave participantu,
- vytvoreni komentare,
- vytvoreni interni poznamky,
- nahrani prilohy,
- vytvoreni nebo synchronizaci GitLab issue.

Audit vidi pouze:

- `Admin`,
- `DeliveryManager`.

Audit lze filtrovat podle entity.

## 27. Notifikace

Aplikace vytvari notifikace pro dulezite udalosti.

Notifikace vznikaji zejmena pri:

- pozvani partner uzivatele,
- resetu hesla,
- vytvoreni noveho partnerskeho ticketu,
- pridani participanta,
- pridani komentare,
- assignu ticketu,
- unassignu ticketu,
- zmene statusu,
- uzavreni ticketu.

Novy partnersky ticket oznamuje aplikace aktivnim Delivery Managerum.

Udalosti nad ticketem oznamuje aplikace watcherum ticketu.

Neuspesne notifikace lze znovu zpracovat uzivatelem s roli `Admin` nebo `DeliveryManager`.

## 28. Jednoduche partnerske API

Aplikace ma poskytovat jednoduche API pro zakladni integraci partneru.

Prvni verze API ma podporovat pouze:

- vylistovani ticketu konkretniho partnera,
- vytvoreni ticketu u konkretniho partnera.

API nema v prvni verzi resit:

- zmenu stavu ticketu,
- assign ticketu,
- unassign ticketu,
- komentare,
- interni poznamky,
- prilohy,
- spravu klientu,
- spravu uzivatelu,
- spravu participantu,
- GitLab operace.

### 28.1 Pristup k API

API pristup musi byt vzdy vazany na konkretniho partnera.

Volajici API nesmi ziskat ani vytvorit data jineho partnera.

Pokud volajici pozada o partnera, ke kteremu nema opravneni, aplikace musi pozadavek odmitnout.

API nesmi vracet interni tickety.

API nesmi vracet interni poznamky.

API nesmi vracet interni GitLab odkaz.

API muze vracet GitLab status ticketu.

### 28.2 Identifikace partnera

Partner v API muze byt identifikovan:

- internim identifikatorem partnera,
- nebo unikatnim klicem partnera.

Identifikace partnera musi byt jednoznacna.

Pokud partner neexistuje, aplikace vrati chybu.

### 28.3 Vylistovani ticketu partnera

Operace vylistovani ticketu vraci pouze partnerske tickety daneho partnera.

Vystup nesmi obsahovat:

- tickety jinych partneru,
- interni tickety,
- interni poznamky,
- interni GitLab odkazy.

Seznam ticketu ma podporovat strankovani.

Seznam ticketu ma podporovat zakladni filtry:

- status,
- priorita,
- typ ticketu,
- klient,
- textove hledani.

Tickety se radi od nejnovejsich.

Kazdy ticket v seznamu ma obsahovat alespon:

- identifikator ticketu,
- nazev,
- popis,
- typ,
- prioritu,
- status,
- klienta, pokud je nastaven,
- vlastnika, pokud je dostupny,
- GitLab status, pokud existuje,
- datum vytvoreni,
- datum posledni zmeny.

### 28.4 Vytvoreni ticketu partnera

Operace vytvoreni ticketu zaklada novy partnersky ticket pod konkretnim partnerem.

Vstup pro vytvoreni ticketu musi obsahovat:

- typ ticketu,
- prioritu,
- nazev,
- popis.

Vstup pro vytvoreni ticketu muze obsahovat:

- klienta,
- vlastnika,
- externi referenci z partnerskeho systemu.

Typ ticketu musi byt jedna z povolenych hodnot podle sekce `9. Typy ticketu`.

Priorita musi byt jedna z povolenych hodnot podle sekce `10. Priority ticketu`.

Pokud je typ ticketu `Security Issue` a priorita je `Normal`, aplikace nastavi prioritu `Critical`.

Pokud je uveden klient:

- klient musi existovat,
- klient musi patrit ke stejnemu partnerovi,
- vlastnik ticketu musi byt odpovednou osobou daneho klienta.

Vlastnik ticketu musi byt aktivni partner uzivatel s roli `responsible` u stejneho partnera.

Pokud API pozadavek vlastnika neuvede, aplikace musi pouzit vychozi odpovednou osobu partnera.

Pokud partner nema vychozi odpovednou osobu nebo vlastnika nelze jednoznacne urcit, aplikace musi vytvoreni ticketu odmitnout.

Po vytvoreni ticketu plati:

- ticket je partnersky,
- ticket neni interni,
- ticket patri k urcenemu partnerovi,
- ticket ma stav `New`,
- vlastnik se stava participantem,
- vlastnik se stava watcherem,
- ticket se zobrazi ve standardnim seznamu ticketu partnera,
- Delivery Manageri dostanou informaci o novem ticketu.

### 28.5 Externi reference

API muze pri vytvoreni ticketu prijmout externi referenci z partnerskeho systemu.

Externi reference slouzi k dohledani ticketu mezi TicketMasterem a systemem partnera.

Externi reference nesmi nahrazovat identifikator ticketu v TicketMasteru.

Pokud bude API podporovat ochranu proti duplicitam, ma se duplicita vyhodnocovat podle kombinace:

- partner,
- externi reference.

### 28.6 Chybove stavy API

API musi vratit srozumitelnou chybu zejmena pri techto stavech:

- partner neexistuje,
- volajici nema opravneni k partnerovi,
- typ ticketu neni povoleny,
- priorita neni povolena,
- klient neexistuje,
- klient nepatri k partnerovi,
- vlastnik neexistuje,
- vlastnik neni aktivni,
- vlastnik neni odpovedna osoba partnera,
- vlastnik neni odpovedna osoba vybraneho klienta,
- chybi povinne pole.

## 29. Business pravidla podle roli

### 29.1 Admin

`Admin` muze:

- videt vsechny tickety,
- vytvaret partnera,
- vytvaret interni uzivatele,
- vytvaret partner uzivatele,
- vytvaret a upravovat klienty,
- spravovat vazby odpovednych osob ke klientum,
- upravovat interni i partner uzivatele,
- deaktivovat uzivatele pri zachovani ochrany posledniho Admina,
- posilat reset hesla,
- assignovat ticket,
- unassignovat ticket,
- menit stav ticketu,
- uzavrit ticket,
- prevest vlastnictvi partnerskeho ticketu,
- spravovat participanty partnerskeho ticketu,
- pridat komentar,
- pridat interni poznamku,
- spravovat GitLab issue,
- videt audit.

### 29.2 Delivery Manager

`DeliveryManager` muze:

- videt vsechny tickety,
- vytvaret partner uzivatele,
- vytvaret a upravovat klienty,
- spravovat vazby odpovednych osob ke klientum,
- upravovat partner uzivatele,
- deaktivovat partner uzivatele,
- posilat reset hesla partner uzivatelum,
- assignovat ticket,
- unassignovat ticket,
- menit stav ticketu,
- uzavrit ticket,
- prevest vlastnictvi partnerskeho ticketu,
- spravovat participanty partnerskeho ticketu,
- pridat komentar,
- pridat interni poznamku,
- spravovat GitLab issue,
- videt audit.

`DeliveryManager` nesmi spravovat interni uzivatele.

### 29.3 L1, L2, L3

Uzivatel s roli `L1`, `L2` nebo `L3` muze:

- videt tickety sveho resolver teamu,
- videt tickety, ktere jsou mu prirazene,
- videt tickety, ktere vlastni,
- vytvorit interni ticket,
- pridat komentar k ticketu, ktery vidi,
- pridat interni poznamku k ticketu, ktery vidi,
- menit stav ticketu sveho resolver teamu podle workflow,
- assignovat ticket pouze v ramci sveho resolver teamu.

Resolver role nesmi:

- videt vsechny tickety bez omezeni,
- menit resolver team ticketu na jiny tym,
- unassignovat ticket z assignee zpet do fronty,
- spravovat partnery,
- spravovat klienty,
- spravovat uzivatele,
- videt audit.

### 29.4 Odpovedna osoba partnera

Partner uzivatel s roli `responsible` muze:

- vytvorit partnersky ticket,
- videt partnerske tickety sveho partnera,
- pridat komentar k ticketu, kde je participantem,
- spravovat participanty u ticketu, ktery vlastni,
- prevest vlastnictvi ticketu, ktery vlastni,
- videt partner dashboard.

Odpovedna osoba partnera nesmi:

- vytvaret interni ticket,
- menit workflow status ticketu,
- assignovat ticket,
- pridavat interni poznamky,
- videt interni poznamky,
- videt interni tickety,
- spravovat uzivatele,
- spravovat klienty,
- videt audit,
- zakladat nebo synchronizovat GitLab issue.

### 29.5 Technicka osoba partnera

Partner uzivatel s roli `technical` muze:

- videt partnerske tickety sveho partnera,
- pridat komentar k ticketu, kde je participantem,
- videt partner dashboard.

Technicka osoba partnera nesmi:

- vytvorit ticket,
- menit workflow status ticketu,
- assignovat ticket,
- spravovat participanty,
- prevest vlastnictvi ticketu,
- pridavat interni poznamky,
- videt interni poznamky,
- videt interni tickety,
- spravovat uzivatele,
- spravovat klienty,
- videt audit,
- zakladat nebo synchronizovat GitLab issue.

## 30. Finalni souhrn pravidel

- Ticket je trvaly zaznam a nema byt odstranen.
- Partner a klient nemaji aktivni/neaktivni stav.
- Partnera a klienta nelze odstranit.
- Aktivni/neaktivni stav ma pouze uzivatel.
- Odstraneni uzivatele znamena deaktivaci uctu.
- Neaktivni uzivatel se neprihlasi a neprovadi aktivni cinnosti.
- Partnersky ticket zaklada pouze odpovedna osoba partnera.
- Technicka osoba partnera ticket nezaklada.
- Partner vidi pouze tickety sveho partnera a nevidi interni tickety.
- Partner komentuje pouze ticket, kde je participantem.
- Interni poznamky vidi pouze interni uzivatele.
- Komentare a interni poznamky se needituji ani nemazou.
- Resolver team ticketu se po nastaveni nemeni na jiny tym.
- Assignee se meni pouze v ramci stejneho resolver teamu.
- `Admin` a `DeliveryManager` mohou vratit ticket z assignee zpet do fronty stejneho resolver teamu.
- `Closed` je finalni stav ticketu.
- Uzavreny ticket neprijima komentare, interni poznamky, prilohy ani assignment.
- L3 ticket potrebuje GitLab issue pred prechodem do `In progress`.
- GitLab status muze videt i partner, GitLab odkaz je pouze interni.
- Jednoduche partnerske API umi v prvni verzi pouze vylistovat tickety partnera a vytvorit ticket pod partnerem.
