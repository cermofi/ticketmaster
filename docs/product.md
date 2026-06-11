# Product Guide

TicketMaster eviduje tri druhy ticketu:

- partnersky ticket,
- interni ticket,
- system ticket.

Podrobna business pravidla jsou v [TicketMaster - aplikacni logika](ticketmaster_aplikacni_logika.md).

## Uzivatele

| Skupina | Role |
| --- | --- |
| Interni | `Admin`, `DeliveryManager`, `L1`, `L2`, `L3` |
| Partner | `responsible`, `technical` |

`DeliveryManager` ma podobna business opravneni jako Admin, ale nespravuje interni Admin ucty.

## Partner a klient

Partner sdruzuje partner uzivatele a klienty. Klient patri vzdy pod jednoho partnera. Odpovedne osoby (`responsible`) lze prirazovat ke klientum.

Partner a klient v MVP nemaji active/inactive stav a nemazou se.

## Partnersky ticket

Partnersky ticket zaklada odpovedna osoba partnera. Muze byt navazan na klienta. Pokud je navazan na klienta, vlastnik ticketu musi byt odpovednou osobou pro dany klient.

`Admin` nebo `DeliveryManager` muze vytvorit partnersky ticket za partnera. Autor ticketu je interni uzivatel, vlastnik ticketu je vybrana odpovedna osoba partnera.

## Interni ticket

Interni ticket zaklada interni uzivatel. Nema partnera ani klienta. Viditelnost resolver roli je dana resolver teamem.

## System ticket

System ticket zaklada aplikace, automatizace, integrace nebo jednoduche partnerske API. Patri ke konkretnimu partnerovi, ale nema klienta, vlastnika ani autora.

System ticket vidi partner, ke kteremu patri. Komentovat ho za partnera smi pouze odpovedna osoba.

## Uzavrene tickety

Closed ticket je finalni. Nelze ho komentovat, doplnovat interni poznamkou, prirazovat ani znovu otevrit.

## Custom vlastnik

Custom vlastnik ticketu je volitelny interni text. Vidi ho interni uzivatele a meni ho pouze `Admin` nebo `DeliveryManager`. Nema vliv na vlastnika ticketu, assignee, participanty, watchery ani workflow.

## Export ticketu

Export ticketu je dostupny ze seznamu ticketu ve formatu JSON, XLSX nebo CSV ZIP. Export respektuje aktualni filtry a prava uzivatele. Partner neexportuje interni poznamky, GitLab odkaz ani custom vlastnika.
