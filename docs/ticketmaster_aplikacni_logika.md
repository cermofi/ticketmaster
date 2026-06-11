
# TicketMaster - aplikacni logika

Tento dokument popisuje funkcni pravidla aplikace TicketMaster.

## Obsah

1. Definice pojmu
2. Ucel aplikace
3. Uzivatele, role a ucty
4. Partneri, klienti a odpovedne osoby
5. Ticket jako hlavni entita
6. Druhy ticketu
7. Typy, priority a statusy ticketu
8. Vytvoreni ticketu
9. Viditelnost, seznamy a hledani ticketu
10. Workflow ticketu
11. Resolver team, assignee a fronta
12. Vlastnictvi ticketu
13. Participanti a watcheri
14. Komunikace a prilohy
15. GitLab logika
16. Partner dashboard
17. Jednoduche partnerske API
18. Administrace, audit a notifikace
19. Finalni souhrn pravidel
20. Permission matrix

## 1. Definice pojmu

### 1.1 Zakladni pojmy

| Pojem | Definice |
| --- | --- |
| TicketMaster | Aplikace pro evidenci, predavani a reseni ticketu mezi partnery, internim tymem a systemovymi integracemi. |
| Ticket | Hlavni pracovni a historicky zaznam v aplikaci. Ticket se neodstranuje. |
| Druh ticketu | Procesni kategorie ticketu podle puvodu a vazeb: partnersky ticket, interni ticket nebo system ticket. |
| Typ ticketu | Vecna kategorie pozadavku, napr. `Problem`, `Question` nebo `Security Issue`. |
| Partner | Organizace nebo skupina, pod kterou patri partner uzivatele a klienti. |
| Klient | Subjekt nebo system evidovany pod partnerem. |
| Interni uzivatel | Uzivatel na strane interni organizace. Ma jednu interni roli. |
| Partner uzivatel | Uzivatel konkretniho partnera. Ma jednu partner roli. |
| Odpovedna osoba | Partner uzivatel s roli `responsible`. Muze zakladat partnerske tickety, byt vlastnikem partnerskeho ticketu a komentovat system tickety sveho partnera. |
| Technicka osoba | Partner uzivatel s roli `technical`. Muze komentovat partnersky ticket, pokud je participantem. Ticket nezaklada. |
| Vlastnik ticketu | Hlavni odpovedna osoba za partnersky ticket. U interniho ticketu je vlastnik zakladajici interni uzivatel. System ticket vlastnika nema. |
| Autor ticketu | Uzivatel, ktery ticket zalozil. System ticket autora nema. |
| Participant | Partner uzivatel zapojeny do komunikace partnerskeho nebo system ticketu daneho partnera. |
| Watcher | Uzivatel, kteremu aplikace posila informace o udalostech ticketu. |
| Resolver team | Interni resitelske oddeleni `L1`, `L2` nebo `L3`. |
| Assignee | Konkretni interni uzivatel prirazeny k reseni ticketu. |
| Fronta | Ticket v resolver teamu bez konkretniho assignee. |
| Internal note | Interni poznamka viditelna pouze internim uzivatelum. |
| Verejny komentar | Komentar viditelny v komunikaci ticketu podle pravidel viditelnosti. |
| GitLab issue | Vyvojove issue navazane na L3 praci. |
| GitLab status | Doplnkovy stav GitLab issue. Muze byt viditelny i partnerovi. |
| GitLab odkaz | Odkaz na GitLab issue. Je viditelny pouze internim uzivatelum. |
| Jednoduche partnerske API | Zakladni integracni rozhrani pro partnera. Prvni verze umi vylistovat tickety partnera a vytvorit system ticket pro partnera. |

### 1.2 Rozliseni druhu a typu ticketu

Pojem `druh ticketu` urcuje, odkud ticket pochazi a jake ma vazby:

- partnersky ticket,
- interni ticket,
- system ticket.

Pojem `typ ticketu` urcuje vecny obsah pozadavku:

- `Problem`,
- `Change Request`,
- `New Feature`,
- `Question`,
- `Configuration`,
- `Integration`,
- `Security Issue`,
- `Operational Request`.

Tyto pojmy se nesmi zamenovat. `System ticket` je druh ticketu, ne vecny typ pozadavku.

## 2. Ucel aplikace

TicketMaster je aplikace pro evidenci a rizeni pozadavku.

Aplikace pokryva tyto hlavni scenare:

- partner zaklada a sleduje partnerske tickety,
- interni uzivatel zaklada a resi interni tickety,
- system nebo integrace zaklada system tickety pro konkretniho partnera,
- Delivery Manager nebo Admin provadi triaz a smerovani,
- resolver teamy `L1`, `L2` a `L3` resi prirazene tickety,
- interni tym komunikuje pres komentare a interni poznamky,
- partner komunikuje pres verejne komentare,
- L3 prace musi byt navazana na GitLab issue.

Ticket je trvaly zaznam aplikace. Ticket nesmi zmizet z evidence.

## 3. Uzivatele, role a ucty

### 3.1 Typy uzivatelu

Uzivatel je bud:

- interni uzivatel,
- partner uzivatel.

Interni uzivatel patri do interni organizace.

Partner uzivatel patri prave k jednomu partnerovi.

### 3.2 Interni role

Interni role jsou:

- `Admin`
- `DeliveryManager`
- `L1`
- `L2`
- `L3`

`DeliveryManager` ma v business procesech podobna prava jako `Admin`, ale nesmi spravovat interni ucty s roli `Admin`.

### 3.3 Partner role

Partner role jsou:

- `responsible`
- `technical`

`responsible` znamena odpovedna osoba partnera.

`technical` znamena technicka osoba partnera.

### 3.4 Aktivni a neaktivni ucet

Stav aktivni/neaktivni existuje pouze u uzivatelu.

Neaktivni uzivatel:

- se nemuze prihlasit,
- nemuze zalozit ticket,
- nemuze pridat komentar,
- nemuze pridat interni poznamku,
- nema provadet zadnou aktivni cinnost v aplikaci.

Pri prihlaseni neaktivniho uzivatele aplikace vraci chybu, ze ucet neni aktivni.

### 3.5 Ochrana Admin uctu

Aplikace musi chranit posledni aktivni `Admin` ucet.

Nelze:

- deaktivovat posledniho aktivniho Admina,
- zmenit roli posledniho aktivniho Admina tak, aby v aplikaci nezustal zadny aktivni Admin.

Uzivatel nesmi deaktivovat sam sebe.

### 3.6 Prihlaseni a aktivace

Interni uzivatel se prihlasuje internim prihlasovacim tokem.

Interni uzivatel musi byt predem zalozeny v aplikaci.

Partner uzivatel se prihlasuje e-mailem a heslem.

Partner uzivatel vznikne pozvankou.

Pozvanka obsahuje aktivacni token, pomoci ktereho si uzivatel nastavi heslo.

Heslo musi mit alespon 8 znaku.

Reset hesla vytvori novy token pro nastaveni hesla.

Reset hesla lze poslat pouze aktivnimu uzivateli.

U interniho uzivatele smi reset hesla vyvolat pouze `Admin`.

## 4. Partneri, klienti a odpovedne osoby

### 4.1 Partner

Partner reprezentuje organizaci nebo skupinu, pod kterou patri partner uzivatele a klienti.

Partner ma:

- identifikator,
- unikatni klic,
- nazev,
- datum vytvoreni.

Partnera smi zalozit `Admin` nebo `DeliveryManager`.

Partnera nelze odstranit.

Partneri jsou viditelni pro `Admin` a `DeliveryManager`.

Partner uzivatel nevidi seznam partneru.

### 4.2 Klient

Klient je subjekt nebo system v ramci partnera.

Klient patri prave k jednomu partnerovi.

Klient ma:

- identifikator,
- unikatni klic,
- partnera,
- nazev,
- datum vytvoreni.

Klienta smi zalozit `Admin` nebo `DeliveryManager`.

Klienta smi prejmenovat `Admin` nebo `DeliveryManager`.

Klienta nelze odstranit.

Partner uzivatel vidi klienty sveho partnera.

Interni uzivatele s roli `Admin` nebo `DeliveryManager` vidi klienty napric partnery a mohou je filtrovat podle partnera.

### 4.3 Vazba klienta a odpovedne osoby

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

### 4.4 Sprava uzivatelu

Interniho uzivatele smi vytvorit pouze `Admin`.

`DeliveryManager` muze spravovat bezne uzivatele, ale nesmi spravovat interni ucty s roli `Admin`.

Partner uzivatele smi vytvorit `Admin` nebo `DeliveryManager`.

U uzivatele lze upravit:

- e-mail,
- jmeno,
- roli,
- aktivni/neaktivni stav.

E-mail musi byt unikatni.

Role musi odpovidat typu uzivatele.

Internimu uzivateli lze nastavit pouze interni roli.

Partner uzivateli lze nastavit pouze partner roli.

Odstraneni uzivatele znamena deaktivaci uctu.

Zaznam uzivatele zustava v aplikaci kvuli historii ticketu, komentaru, auditu a vazeb.

Historicke zaznamy ticketu musi zachovat informaci o tom, ktery uzivatel akci provedl, i kdyz je uzivatel pozdeji deaktivovan.

## 5. Ticket jako hlavni entita

Ticket je hlavni pracovni jednotka aplikace.

Ticket musi byt prave jednoho druhu:

- partnersky ticket,
- interni ticket,
- system ticket.

Ticket se neodstranuje.

Ticket nesmi byt odstranen ani pri zmene, deaktivaci nebo odstraneni jine navazane entity.

Ticket muze byt:

- bez resolver teamu,
- ve fronte konkretniho resolver teamu,
- prirazeny konkretnimu assignee.

Zakladni informace spolecne pro ticket jsou:

- identifikator,
- druh ticketu,
- typ ticketu,
- priorita,
- stav,
- resolver team,
- assignee,
- nazev,
- popis,
- datum vytvoreni,
- datum posledni zmeny.

## 6. Druhy ticketu

### 6.1 Partnersky ticket

Partnersky ticket zaklada partner uzivatel s roli `responsible`.

Partnersky ticket ma:

- identifikator,
- priznak partnerskeho ticketu,
- partnera,
- volitelne klienta,
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

Partnersky ticket:

- neni interni,
- neni systemovy,
- je viditelny partner uzivatelum daneho partnera,
- muze mit participanty partnera,
- muze mit watchery.

### 6.2 Interni ticket

Interni ticket zaklada interni uzivatel.

Interni ticket ma:

- identifikator,
- priznak interniho ticketu,
- nema partnera,
- nema klienta,
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

Interni ticket:

- neni partnersky,
- neni systemovy,
- neni viditelny partner uzivatelum.

### 6.3 System ticket

System ticket zaklada aplikace, automatizace nebo integrace.

System ticket pokryva pozadavky, ktere nevznikaji primou akci konkretniho uzivatele. Typickym prikladem je ticket zalozeny pres partnerske API nebo jinou systemovou integraci.

System ticket ma:

- identifikator,
- priznak system,
- partnera,
- nema klienta,
- nema vlastnika,
- nema autora,
- typ,
- prioritu,
- stav,
- resolver team,
- assignee,
- nazev,
- popis,
- datum vytvoreni,
- datum posledni zmeny.

System ticket:

- neni partnersky,
- neni interni,
- nema partner vlastnika,
- je viditelny vsem aktivnim uzivatelum daneho partnera,
- partner uzivatele ho mohou komentovat pouze tehdy, pokud maji roli `responsible`,
- osoby na strane partnera mohou pridavat pouze partner uzivatele s roli `responsible`,
- za interni tym ho vidi `Admin`, `DeliveryManager` a resolver role `L1`, `L2` nebo `L3`, pokud ma system ticket nastaveny jejich resolver team,
- muze byt smerovan do resolver teamu,
- muze byt prirazen konkretnimu assignee.

## 7. Typy, priority a statusy ticketu

### 7.1 Typy ticketu

Povolene vecne typy ticketu jsou:

- `Problem`
- `Change Request`
- `New Feature`
- `Question`
- `Configuration`
- `Integration`
- `Security Issue`
- `Operational Request`

Typ ticketu musi byt jedna z povolenych hodnot.

### 7.2 Priority ticketu

Povolene priority jsou:

- `Low`
- `Normal`
- `High`
- `Critical`

Priorita musi byt jedna z povolenych hodnot.

Pokud je typ ticketu `Security Issue` a uzivatel nebo integrace zvoli prioritu `Normal`, aplikace nastavi prioritu `Critical`.

### 7.3 Statusy ticketu

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

## 8. Vytvoreni ticketu

### 8.1 Vytvoreni partnerskeho ticketu

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
- ticket neni systemovy,
- vlastnik se automaticky stava participantem,
- vlastnik se automaticky stava watcherem,
- volitelni participanti musi byt aktivni uzivatele stejneho partnera,
- Delivery Manageri dostanou informaci o novem ticketu.

### 8.2 Vytvoreni interniho ticketu

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
- ticket neni partnersky,
- ticket neni systemovy,
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

Pokud je interni ticket zalozen rovnou pro `L3`, aplikace musi zalozit hlavni GitLab issue.

Pokud se GitLab issue nepodari zalozit, interni ticket nesmi byt vytvoren ani prirazen do `L3`.

### 8.3 Vytvoreni system ticketu

System ticket smi vytvorit pouze aplikace, automatizace nebo integrace s opravnenim zakladat systemove tickety.

Pri zalozeni system ticketu se nastavuje:

- partner,
- typ,
- priorita,
- nazev,
- popis,
- volitelny resolver team,
- volitelne assignee.

Po zalozeni system ticketu plati:

- ticket je systemovy,
- ticket neni partnersky,
- ticket neni interni,
- patri ke konkretnimu partnerovi,
- nema klienta,
- nema vlastnika,
- nema autora,
- je viditelny partner uzivatelum daneho partnera,
- muze mit resolver team,
- muze mit assignee.

Pokud je pri zalozeni vybran resolver team:

- ticket zacina ve stavu `Assigned`,
- resolver team je nastaven na vybranou hodnotu.

Pokud resolver team vybran neni:

- ticket zacina ve stavu `New`,
- resolver team neni nastaven.

Pokud je system ticket zalozen rovnou pro `L3`, aplikace musi zalozit hlavni GitLab issue.

Pokud se GitLab issue nepodari zalozit, system ticket nesmi byt vytvoren ani prirazen do `L3`.

## 9. Viditelnost, seznamy a hledani ticketu

### 9.1 Admin a Delivery Manager

`Admin` a `DeliveryManager` vidi vsechny tickety:

- partnerske,
- interni,
- systemove.

### 9.2 Resolver role L1, L2, L3

Uzivatel s roli `L1`, `L2` nebo `L3` vidi pouze tickety sveho resolver teamu.

Ticket patri do resolver teamu uzivatele tehdy, kdyz ma nastaveny resolver team stejny jako role uzivatele.

System ticket za interni tym vidi `Admin`, `DeliveryManager` a resolver role `L1`, `L2` nebo `L3`, pokud ma system ticket nastaveny jejich resolver team.

### 9.3 Partner uzivatele

Partner uzivatel vidi:

- partnerske tickety sveho partnera,
- system tickety prirazene ke svemu partnerovi.

Partner uzivatel nevidi:

- interni tickety,
- tickety jinych partneru.

Viditelnost ticketu partner uzivatelem neznamena automaticky pravo komentovat.

### 9.4 Seznam a hledani ticketu

Seznam ticketu zobrazuje pouze tickety viditelne pro prihlaseneho uzivatele.

Tickety se radi od nejnovejsich.

Seznam ticketu lze filtrovat podle:

- textoveho hledani,
- statusu,
- priority,
- typu,
- resolver teamu,
- partnera,
- druhu ticketu.

Textove hledani pracuje s:

- identifikatorem ticketu,
- nazvem ticketu,
- popisem ticketu,
- verejnymi komentari.

## 10. Workflow ticketu

### 10.1 Povolene prechody

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
| `Closed` | zadny dalsi prechod |

### 10.2 Kdo muze menit status

Partner uzivatele status ticketu nemeni.

`Admin` a `DeliveryManager` mohou provadet povolene workflow prechody u vsech ticketu.

Uzivatel s roli `L1`, `L2` nebo `L3` muze menit status jen u ticketu sveho resolver teamu.

Resolver role mohou pouzit tyto cilove statusy:

- `In progress`
- `Resolved`
- `Need more info`
- `Assigned`

Prechod do ciloveho statusu musi byt zaroven povolen workflow tabulkou.

Statusy `Rejected`, `Duplicate`, `Cancelled` a `Closed` smi nastavit pouze `Admin` nebo `DeliveryManager`.

### 10.3 Dostupne dalsi stavy

Aplikace ma uzivateli nabizet pouze takove dalsi stavy ticketu, ktere:

- jsou povolene workflow tabulkou,
- odpovidaji roli uzivatele,
- splnuji vsechny business podminky ticketu.

Zakazane prechody se uzivateli nemaji nabizet jako volba.

### 10.4 Need more info

`Need more info` znamena, ze ticket ceka na doplneni informaci.

Do stavu `Need more info` lze prejit:

- z `New`,
- z `Assigned`,
- z `In progress`.

Ze stavu `Need more info` lze pokracovat:

- automaticky zpet po pridani verejneho komentare,
- manualne zpet pomoci `Admin` nebo `DeliveryManager`,
- na `New`, pokud ticket nema resolver team,
- na `Assigned`,
- na `Rejected`,
- na `Cancelled`.

Partner nemeni status ticketu. Partner doplni informace pouze pridanim verejneho komentare.

Po pridani verejneho komentare do ticketu ve stavu `Need more info` aplikace automaticky vrati ticket:

- do stavu `Assigned`, pokud ma ticket resolver team,
- do stavu `New`, pokud ticket resolver team nema.

### 10.5 Uzavreny ticket

Ticket ve stavu `Closed` je uzavreny.

`Resolved` znamena, ze je ticket vyreseny z pohledu interniho tymu.

`Closed` znamena finalni uzavreni ticketu.

U uzavreneho ticketu:

- nelze pridat komentar,
- nelze pridat interni poznamku,
- nelze nahrat prilohu, protoze prilohu smi nahrat jen uzivatel s pravem komentovat,
- nelze provest assign,
- nelze provest unassign,
- nelze provest dalsi workflow prechod.

`Closed` je nevratny stav.

Ticket smi uzavrit pouze `Admin` nebo `DeliveryManager`.

Partner uzivatel ani resolver role `L1`, `L2` a `L3` ticket neuzaviraji.

## 11. Resolver team, assignee a fronta

### 11.1 Resolver team

Resolver team je jedna z hodnot:

- `L1`
- `L2`
- `L3`

Resolver team urcuje oddeleni, ktere ticket resi.

Jakmile je resolver team nastaven, ticket nesmi prejit do jineho resolver teamu.

### 11.2 Assignee

Assignee je konkretni interni uzivatel prirazeny k ticketu.

Assignee musi byt interni uzivatel ze stejneho resolver teamu jako ticket.

Assignee se muze menit v ramci stejneho resolver teamu.

U system ticketu je pro viditelnost resolver role rozhodujici resolver team. Assignee musi byt ze stejneho resolver teamu.

### 11.3 Assign

Assign nastavuje:

- resolver team,
- volitelne assignee,
- stav ticketu na `Assigned`.

Assign nelze provest u ticketu ve stavu `Closed`.

`Admin` a `DeliveryManager` mohou assignovat ticket do libovolneho povoleneho resolver teamu, pokud tim nedojde ke zmene uz nastaveneho resolver teamu.

Resolver role muze assignovat pouze ticket, ktery uz patri do jejiho resolver teamu, a pouze zpet do stejneho resolver teamu.

Pokud je ticket assignovan na `L3`, aplikace musi zalozit hlavni GitLab issue.

Pokud se GitLab issue nepodari zalozit, assign do `L3` se neprovede a ticket zustane v puvodnim stavu.

### 11.4 Unassign

Unassign vraci ticket z konkretniho assignee zpet do fronty stejneho resolver teamu.

Unassign:

- smi provest pouze `Admin` nebo `DeliveryManager`,
- nelze provest u ticketu ve stavu `Closed`,
- vyzaduje, aby ticket mel resolver team,
- nastavi assignee na prazdnou hodnotu,
- zachova resolver team,
- nastavi stav ticketu na `Assigned`.

## 12. Vlastnictvi ticketu

### 12.1 Vlastnik partnerskeho ticketu

Vlastnikem partnerskeho ticketu je odpovedna osoba partnera.

Vlastnik:

- je hlavni odpovedna osoba za ticket na strane partnera,
- je automaticky participant,
- je automaticky watcher,
- nemuze byt odebran z participantu.

### 12.2 Vlastnik interniho ticketu

Vlastnikem interniho ticketu je interni uzivatel, ktery ticket zalozil.

Interni ticket nema partner ownera.

### 12.3 System ticket bez vlastnika

System ticket nema vlastnika.

System ticket nema autora.

System ticket nema partner ownera.

System ticket patri ke konkretnimu partnerovi, ale nema klienta.

System ticket muze mit osoby pridane do komunikace, ale jejich pridani nevytvari vlastnictvi ticketu.

### 12.4 Prevod vlastnictvi

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

## 13. Participanti a watcheri

### 13.1 Participant

Participant je partner uzivatel zapojeny do komunikace ticketu partnera.

U partnerskeho ticketu muze participant pridavat verejne komentare, pokud muze ticket videt a ticket neni uzavreny.

U system ticketu smi verejny komentar pridat pouze partner uzivatel s roli `responsible`.

Participanty lze spravovat u partnerskeho ticketu.

Spravu participantu smi provest:

- vlastnik ticketu,
- `Admin`,
- `DeliveryManager`.

Participant musi byt uzivatel stejneho partnera jako ticket.

Vlastnika ticketu nelze odebrat z participantu.

U system ticketu mohou osoby na strane partnera pridavat pouze partner uzivatele s roli `responsible`.

Interni ticket nema partner participanty.

### 13.2 Watcher

Watcher je uzivatel, ktery dostava informace o udalostech ticketu.

Participant se automaticky stava watcherem.

Assignee se automaticky stava watcherem.

Zakladajici uzivatel interniho ticketu se automaticky stava watcherem.

System ticket muze mit watchery podle pravidel udalosti a assignmentu.

## 14. Komunikace a prilohy

### 14.1 Verejny komentar

Verejny komentar je viditelny uzivatelum s pravem videt ticket.

Komentar smi pridat:

- aktivni interni uzivatel, ktery ticket vidi,
- aktivni partner uzivatel, ktery je participantem partnerskeho ticketu,
- aktivni partner uzivatel s roli `responsible`, pokud jde o system ticket jeho partnera.

Komentar nelze pridat u ticketu ve stavu `Closed`.

Partner uzivatel nemuze komentovat interni ticket.

Partner uzivatel s roli `technical` nemuze komentovat system ticket.

### 14.2 Interni poznamka

Interni poznamku vidi pouze interni uzivatele.

Interni poznamku smi pridat aktivni interni uzivatel, ktery ticket vidi.

Partner uzivatel interni poznamku nevidi.

Interni poznamku nelze pridat u ticketu ve stavu `Closed`.

### 14.3 Editace a mazani komunikace

Komentare a interni poznamky se v aplikaci needituji.

Komentare a interni poznamky se v aplikaci nemazou.

Komentare, interni poznamky a tickety jsou trvale historicke zaznamy.

### 14.4 Prilohy

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

## 15. GitLab logika

GitLab je navazany na reseni ticketu v teamu `L3`.

### 15.1 Hlavni GitLab issue

Ticket muze mit hlavni GitLab issue.

Jeden ticket muze byt napojen pouze na jedno hlavni GitLab issue.

Aplikace musi zalozit hlavni GitLab issue:

- pri assignu ticketu na `L3`,
- pri vytvoreni interniho ticketu s resolver teamem `L3`,
- pri vytvoreni system ticketu s resolver teamem `L3`.

Bez hlavniho GitLab issue se ticket nesmi priradit do resolver teamu `L3`.

Pokud se zalozeni GitLab issue nepodari, prirazeni do `L3` se neprovede.

### 15.2 GitLab status

GitLab status muze byt:

- `Open`
- `To Do`
- `In Progress`
- `Done`
- `Closed`

Partner muze videt GitLab status u partnerskeho ticketu jako doplnkovou informaci.

Partner muze videt GitLab status i u system ticketu sveho partnera.

GitLab odkaz je viditelny pouze internim uzivatelum.

Partner nikdy nevidi GitLab odkaz.

### 15.3 Guard pro L3 praci

Ticket v resolver teamu `L3` nesmi prejit do stavu `In progress`, pokud nema hlavni GitLab issue.

### 15.4 Synchronizace GitLab statusu

GitLab status smi synchronizovat pouze interni uzivatel.

Pokud GitLab issue neexistuje, synchronizace neni mozna.

## 16. Partner dashboard

Partner dashboard je dostupny pouze partner uzivateli.

Partner dashboard zobrazuje:

- klienty partnera,
- odpovedne osoby u jednotlivych klientu,
- informaci, zda je prihlaseny uzivatel odpovednou osobou daneho klienta,
- technicke osoby partnera.

Technicke osoby jsou vedeny jako samostatny seznam partner uzivatelu s roli `technical`.

System tickety se nezobrazuji v prehledu klientu, protoze nemaji klienta.

System tickety prirazene partnerovi se zobrazuji v seznamu ticketu partnera.

## 17. Jednoduche partnerske API

Aplikace ma poskytovat jednoduche API pro zakladni integraci partneru.

Prvni verze API ma podporovat pouze:

- vylistovani ticketu konkretniho partnera,
- vytvoreni system ticketu pro konkretniho partnera.

### 17.1 Rozsah prvni verze API

API nema v prvni verzi resit:

- vytvareni partnerskych ticketu,
- zmenu stavu ticketu,
- assign ticketu,
- unassign ticketu,
- komentare,
- interni poznamky,
- prilohy,
- spravu klientu,
- spravu uzivatelu,
- spravu participantu,
- GitLab operace,
- externi identifikatory,
- ochranu proti duplicitam.

### 17.2 Pristup k API

API pristup musi byt vzdy vazany na konkretniho partnera.

Volajici API nesmi ziskat data jineho partnera.

Pokud volajici pozada o partnera, ke kteremu nema opravneni, aplikace musi pozadavek odmitnout.

API nesmi vracet:

- interni tickety,
- interni poznamky,
- interni GitLab odkazy.

API muze vracet:

- partnerske tickety daneho partnera,
- system tickety prirazene danemu partnerovi,
- GitLab status ticketu, pokud existuje.

### 17.3 Identifikace partnera

Partner v API muze byt identifikovan:

- internim identifikatorem partnera,
- nebo unikatnim klicem partnera.

Identifikace partnera musi byt jednoznacna.

Pokud partner neexistuje, aplikace vrati chybu.

### 17.4 Vylistovani ticketu partnera

Operace vylistovani ticketu vraci tickety viditelne pro daneho partnera.

To znamena:

- partnerske tickety daneho partnera,
- system tickety prirazene danemu partnerovi.

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
- druh ticketu,
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

### 17.5 Vytvoreni ticketu pres API

API muze v MVP vytvorit pouze system ticket pro konkretniho partnera.

API nesmi vytvorit partnersky ticket.

System ticket vytvoreny pres API:

- je systemovy,
- patri ke konkretnimu partnerovi,
- nema klienta,
- nema vlastnika,
- nema autora,
- je viditelny vsem aktivnim uzivatelum daneho partnera,
- komentovat ho mohou pouze odpovedne osoby daneho partnera,
- osoby na strane partnera mohou pridavat pouze odpovedne osoby daneho partnera.

### 17.6 Vytvoreni system ticketu pres API

Vstup pro vytvoreni system ticketu musi obsahovat:

- typ ticketu,
- prioritu,
- nazev,
- popis.

Vstup muze obsahovat:

- resolver team,
- assignee.

Typ ticketu musi byt jedna z povolenych hodnot podle sekce `7.1 Typy ticketu`.

Priorita musi byt jedna z povolenych hodnot podle sekce `7.2 Priority ticketu`.

Po vytvoreni system ticketu pres API plati:

- ticket je systemovy,
- ticket neni partnersky,
- ticket neni interni,
- patri k urcenemu partnerovi,
- nema klienta,
- nema vlastnika,
- nema autora,
- ticket se zobrazuje v partnerskem seznamu ticketu,
- za interni tym ho vidi `Admin`, `DeliveryManager` a resolver role `L1`, `L2` nebo `L3`, pokud ma system ticket nastaveny jejich resolver team.

Pokud je uveden resolver team, musi byt jedna z hodnot:

- `L1`,
- `L2`,
- `L3`.

Pokud je uveden assignee, musi byt interni uzivatel ze stejneho resolver teamu.

Pokud je uveden resolver team `L3`, aplikace musi zalozit hlavni GitLab issue.

Pokud se GitLab issue nepodari zalozit, vytvoreni system ticketu v `L3` se odmitne.

### 17.7 Chybove stavy API

API musi vratit srozumitelnou chybu zejmena pri techto stavech:

- partner neexistuje,
- volajici nema opravneni k partnerovi,
- typ ticketu neni povoleny,
- priorita neni povolena,
- resolver team neni povoleny,
- assignee neni interni uzivatel ze stejneho resolver teamu,
- GitLab issue se nepodarilo zalozit pri prirazeni do `L3`,
- chybi povinne pole.

## 18. Administrace, audit a notifikace

### 18.1 Audit

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

U zmen ticketu audit uklada starou i novou hodnotu.

Audit vidi pouze:

- `Admin`,
- `DeliveryManager`.

Audit lze filtrovat podle entity.

### 18.2 Notifikace

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

Novy partnersky ticket oznamuje aplikace:

- aktivnim Delivery Managerum,
- uzivateli, ktery ticket zalozil.

Novy system ticket vytvoreny pres API oznamuje aplikace aktivnim Delivery Managerum.

Komentar od partnera oznamuje aplikace:

- aktivnim Delivery Managerum, pokud ticket nema assignee,
- assignee, pokud ticket assignee ma.

Interni komentar nevytvari e-mailovou notifikaci.

Interni poznamka nevytvari e-mailovou notifikaci.

Zmena GitLab statusu nevytvari e-mailovou notifikaci partnerovi.

Udalosti nad ticketem oznamuje aplikace watcherum ticketu pouze tehdy, pokud tento dokument neurcuje konkretni vyjimku.

Neuspesna notifikace se v MVP zapise do audit logu.

MVP nemusi resit opakovane odesilani neuspesnych notifikaci.

## 19. Finalni souhrn pravidel

- Dokument rozlisuje druh ticketu a typ ticketu.
- Druhy ticketu jsou partnersky ticket, interni ticket a system ticket.
- System ticket ma priznak system, patri ke konkretnimu partnerovi a nema klienta, vlastnika ani autora.
- Ticket je trvaly zaznam a nema byt odstranen.
- Partnera a klienta nelze odstranit.
- Aktivni/neaktivni stav ma pouze uzivatel.
- Odstraneni uzivatele znamena deaktivaci uctu.
- Neaktivni uzivatel se neprihlasi a neprovadi aktivni cinnosti.
- Partnersky ticket zaklada pouze odpovedna osoba partnera.
- Technicka osoba partnera ticket nezaklada.
- Partner vidi partnerske tickety sveho partnera a system tickety prirazene svemu partnerovi.
- Partner nevidi interni tickety ani tickety jinych partneru.
- Partner komentuje partnersky ticket, kde je participantem.
- System ticket smi za partnera komentovat pouze odpovedna osoba.
- Interni poznamky vidi pouze interni uzivatele.
- Komentare, interni poznamky a tickety se nikdy nemazou.
- Resolver team ticketu se po nastaveni nemeni na jiny tym.
- Assignee se meni pouze v ramci stejneho resolver teamu.
- `Admin` a `DeliveryManager` mohou vratit ticket z assignee zpet do fronty stejneho resolver teamu.
- `L1`, `L2` a `L3` vidi pouze tickety sveho resolver teamu.
- System ticket za interni tym vidi `Admin`, `DeliveryManager` a resolver role podle nastaveneho resolver teamu.
- `Closed` je finalni stav ticketu.
- Uzavreny ticket neprijima komentare, interni poznamky, prilohy ani assignment.
- Bez GitLab issue se ticket nesmi priradit do `L3`.
- L3 ticket potrebuje GitLab issue pred prechodem do `In progress`.
- GitLab status muze videt i partner, GitLab odkaz je pouze interni.
- Jednoduche partnerske API umi v prvni verzi vylistovat tickety partnera a vytvorit system ticket pro partnera.

## 20. Permission matrix

### 20.1 Zkratky

| Zkratka | Vyznam |
| --- | --- |
| Ano | Role muze akci provest. |
| Ne | Role akci nesmi provest. |
| Omezene | Role muze akci provest jen za podminek uvedenych v dokumentu. |
| System | Akci provadi aplikace, automatizace nebo integrace. |

### 20.2 Uzivatele, partneri a klienti

| Akce | Admin | Delivery Manager | L1/L2/L3 | Odpovedna osoba | Technicka osoba | System/API |
| --- | --- | --- | --- | --- | --- | --- |
| Vytvorit partnera | Ano | Ano | Ne | Ne | Ne | Ne |
| Zobrazit seznam partneru | Ano | Ano | Ne | Ne | Ne | Ne |
| Odstranit partnera | Ne | Ne | Ne | Ne | Ne | Ne |
| Vytvorit klienta | Ano | Ano | Ne | Ne | Ne | Ne |
| Upravit klienta | Ano | Ano | Ne | Ne | Ne | Ne |
| Odstranit klienta | Ne | Ne | Ne | Ne | Ne | Ne |
| Zobrazit klienty partnera | Ano | Ano | Ne | Ano | Ano | Omezene |
| Priradit odpovednou osobu ke klientovi | Ano | Ano | Ne | Ne | Ne | Ne |
| Odebrat odpovednou osobu od klienta | Ano | Ano | Ne | Ne | Ne | Ne |
| Vytvorit interniho uzivatele | Ano | Omezene | Ne | Ne | Ne | Ne |
| Vytvorit partner uzivatele | Ano | Ano | Ne | Ne | Ne | Ne |
| Upravit interniho uzivatele | Ano | Omezene | Ne | Ne | Ne | Ne |
| Upravit partner uzivatele | Ano | Ano | Ne | Ne | Ne | Ne |
| Deaktivovat uzivatele | Omezene | Omezene | Ne | Ne | Ne | Ne |
| Poslat reset hesla | Ano | Omezene | Ne | Ne | Ne | Ne |

### 20.3 Vytvareni a viditelnost ticketu

| Akce | Admin | Delivery Manager | L1/L2/L3 | Odpovedna osoba | Technicka osoba | System/API |
| --- | --- | --- | --- | --- | --- | --- |
| Vytvorit partnersky ticket | Ne | Ne | Ne | Ano | Ne | Ne |
| Vytvorit interni ticket | Ano | Ano | Ano | Ne | Ne | Ne |
| Vytvorit system ticket | Ne | Ne | Ne | Ne | Ne | System |
| Videt vsechny tickety | Ano | Ano | Ne | Ne | Ne | Ne |
| Videt partnerske tickety sveho partnera | Ano | Ano | Ne | Ano | Ano | Omezene |
| Videt interni tickety | Ano | Ano | Omezene | Ne | Ne | Ne |
| Videt system tickety | Ano | Ano | Omezene | Omezene | Omezene | Omezene |
| Vylistovat tickety partnera pres API | Ne | Ne | Ne | Ne | Ne | Omezene |

### 20.4 Workflow a assignment

| Akce | Admin | Delivery Manager | L1/L2/L3 | Odpovedna osoba | Technicka osoba | System/API |
| --- | --- | --- | --- | --- | --- | --- |
| Zmenit status ticketu | Ano | Ano | Omezene | Ne | Ne | Ne |
| Zobrazit dostupne dalsi stavy | Ano | Ano | Omezene | Omezene | Omezene | Ne |
| Assign ticketu | Ano | Ano | Omezene | Ne | Ne | Ne |
| Zmenit resolver team po nastaveni | Ne | Ne | Ne | Ne | Ne | Ne |
| Zmenit assignee ve stejnem resolver teamu | Ano | Ano | Omezene | Ne | Ne | Ne |
| Unassign do fronty stejneho resolver teamu | Ano | Ano | Ne | Ne | Ne | Ne |
| Nastavit `Rejected`, `Duplicate` nebo `Cancelled` | Ano | Ano | Ne | Ne | Ne | Ne |
| Uzavrit ticket | Ano | Ano | Ne | Ne | Ne | Ne |

### 20.5 Vlastnictvi, participanti a komunikace

| Akce | Admin | Delivery Manager | L1/L2/L3 | Odpovedna osoba | Technicka osoba | System/API |
| --- | --- | --- | --- | --- | --- | --- |
| Prevest vlastnictvi partnerskeho ticketu | Ano | Ano | Ne | Omezene | Ne | Ne |
| Prevest vlastnictvi interniho ticketu | Ne | Ne | Ne | Ne | Ne | Ne |
| Prevest vlastnictvi system ticketu | Ne | Ne | Ne | Ne | Ne | Ne |
| Spravovat participanty partnerskeho ticketu | Ano | Ano | Ne | Omezene | Ne | Ne |
| Spravovat osoby system ticketu | Ne | Ne | Ne | Omezene | Ne | Ne |
| Odebrat vlastnika z participantu | Ne | Ne | Ne | Ne | Ne | Ne |
| Pridat verejny komentar | Omezene | Omezene | Omezene | Omezene | Omezene | Ne |
| Pridat komentar k system ticketu | Omezene | Omezene | Omezene | Omezene | Ne | Ne |
| Pridat interni poznamku | Omezene | Omezene | Omezene | Ne | Ne | Ne |
| Editovat komentar nebo interni poznamku | Ne | Ne | Ne | Ne | Ne | Ne |
| Mazat komentar nebo interni poznamku | Ne | Ne | Ne | Ne | Ne | Ne |
| Nahrat prilohu | Omezene | Omezene | Omezene | Omezene | Omezene | Ne |
| Stahnout prilohu | Omezene | Omezene | Omezene | Omezene | Omezene | Ne |

### 20.6 GitLab, audit a notifikace

| Akce | Admin | Delivery Manager | L1/L2/L3 | Odpovedna osoba | Technicka osoba | System/API |
| --- | --- | --- | --- | --- | --- | --- |
| Zalozit GitLab issue rucne | Ano | Ano | Omezene | Ne | Ne | Ne |
| Synchronizovat GitLab status | Ano | Ano | Omezene | Ne | Ne | Ne |
| Videt GitLab status | Ano | Ano | Omezene | Omezene | Omezene | Omezene |
| Videt GitLab odkaz | Ano | Ano | Omezene | Ne | Ne | Ne |
| Videt audit | Ano | Ano | Ne | Ne | Ne | Ne |
| Znovu zpracovat neuspesne notifikace | Ne | Ne | Ne | Ne | Ne | Ne |
