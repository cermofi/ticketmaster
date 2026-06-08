# Security

TicketMaster obsahuje nekolik vrstev ochrany: autentizaci, RBAC, audit, rate-limit, malware scan, security headers a izolaci sluzeb v Docker siti.

## Autentizace

Partner login pouziva e-mail a heslo. Interni login je v MVP reseny dev SSO endpointem pro provisionovane interni uzivatele.

Token se posila jako:

```http
Authorization: Bearer <token>
```

Produkce by mela nahradit dev SSO realnym SSO providerem.

## Hesla a invitation tokeny

Partner uzivatel muze byt pozvan a aktivuje ucet pres invitation token. Password reset vygeneruje novy token a queueuje notifikaci.

Pravidla:

- heslo pri aktivaci musi mit minimalne 8 znaku,
- deaktivace uzivatele maze invitation token,
- nelze deaktivovat posledniho aktivniho Admina.

## Login rate-limit

Login rate-limit je vazany na IP a e-mail:

```text
ticketmaster:login-rate:<ip>:<email>
```

Pokud Redis neni dostupny, API pouziva in-memory fallback. Po uspesnem loginu se stav smaze.

Konfigurace:

- `LOGIN_RATE_LIMIT_ATTEMPTS`
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`

## RBAC

Frontend skryva nepovolene akce, ale API vynucuje opravneni v service vrstve. Rozhodujici logika je v `ticketmaster/services/tickets.py` a `ticketmaster/services/admin.py`.

Kriticke pravidlo: nikdy nespolehat jen na UI. Kazdy zapis musi projit backendovou kontrolou.

## Audit log

Audit log uklada:

- typ entity,
- ID entity,
- akci,
- stare hodnoty,
- nove hodnoty,
- actor user ID,
- source (`ui`, `cli`, `system`),
- cas zmeny.

Loginy a login failures se take audituji vcetne IP, `X-Forwarded-For` a user-agent.

## Security headers

API middleware nastavuje:

- `X-Request-ID`,
- `X-Content-Type-Options: nosniff`,
- `X-Frame-Options: DENY`,
- `Referrer-Policy: strict-origin-when-cross-origin`.

Frontend nginx nastavuje:

- `X-Content-Type-Options`,
- `X-Frame-Options`,
- `Referrer-Policy`,
- `Permissions-Policy`.

## Upload security

Uploady jsou omezeny:

- max 25 MB,
- povolene pripony `.png`, `.jpg`, `.jpeg`, `.pdf`, `.txt`, `.log`, `.zip`,
- ClamAV scan pred ulozenim,
- download vyzaduje view opravneni k ticketu.

Soubor se uklada pod generovanym attachment ID, ne primo pod puvodnim nazvem.

## CORS a trusted hosts

Produkce musi nastavit konkretni hodnoty:

```env
CORS_ORIGINS=https://ticketmaster.example.com
TRUSTED_HOSTS=ticketmaster.example.com,localhost,127.0.0.1
```

Vychozi `*` je vhodne jen pro development.

## Secrets

Tyto hodnoty musi byt v produkci zmenene:

- `APP_SECRET`,
- `POSTGRES_PASSWORD`,
- `SMTP_PASSWORD`,
- `GITLAB_TOKEN`,
- `GRAFANA_ADMIN_PASSWORD`,
- `SENTRY_DSN`, pokud se pouziva.

`.env` nepatri do verejneho repozitare.

## Sentry

Sentry SDK je aktivni pouze pri nastavenem `SENTRY_DSN`. Do Sentry neodesilat citliva data, tokeny ani hesla. Pri rozsireni telemetry pridavat scrub pravidla pro request bodies.

