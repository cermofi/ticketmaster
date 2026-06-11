# Security

TicketMaster je MVP aplikace, ale backend stale vynucuje zakladni bezpecnostni pravidla.

## Autentizace

- Partner uzivatel se prihlasuje e-mailem a heslem.
- Interni uzivatel v MVP pouziva dev SSO endpoint pro provisionovane ucty.
- Chranene endpointy vyzaduji Bearer token.
- Neaktivni uzivatel se nemuze prihlasit ani provadet aktivni akce.

## Hesla a tokeny

- Heslo pri aktivaci/resetu musi mit alespon 8 znaku.
- Pozvanka a reset hesla pouzivaji nahodny token.
- Deaktivace uzivatele maze invitation token.
- Posledni aktivni Admin je chraneny proti deaktivaci a zmene role.

## Rate limit

Login rate limit je v pameti API procesu a je vazany na IP + e-mail. Po restartu API se vynuluje.

Konfigurace:

- `LOGIN_RATE_LIMIT_ATTEMPTS`
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`

## RBAC

Frontend skryva nepovolene akce, ale rozhodujici ochrana je v backend service vrstve:

- `services/tickets.py`,
- `services/admin.py`.

Kazdy zapis musi projit backendovou kontrolou.

## Izolace dat

- Partner vidi jen tickety sveho partnera a nevidi interni tickety.
- Partner nevidi interni poznamky.
- Partner vidi GitLab status, ale ne GitLab URL.
- Resolver role vidi jen tickety sveho resolver teamu.
- System ticket vidi partner, ke kteremu patri, a interni role podle resolver teamu.

## Uploady

Upload je povoleny jen uzivateli, ktery muze k ticketu komentovat.

Limity:

- max 25 MB,
- pripony `.png`, `.jpg`, `.jpeg`, `.pdf`, `.txt`, `.log`, `.zip`,
- download vzdy kontroluje opravneni k ticketu.

Soubor se uklada pod generovanym attachment ID, ne primo pod puvodnim nazvem.

## Security headers

API a nginx nastavují zakladni headers:

- `X-Content-Type-Options: nosniff`,
- `X-Frame-Options: DENY`,
- `Referrer-Policy: strict-origin-when-cross-origin`,
- `Permissions-Policy` na frontendu.

## Secrets

V produkci zmenit:

- `APP_SECRET`,
- `POSTGRES_PASSWORD`,
- `SMTP_PASSWORD`, pokud se pouziva,
- `GITLAB_TOKEN`, pokud se pouziva realny GitLab.

Soubor `.env` nepatri do repozitare.
