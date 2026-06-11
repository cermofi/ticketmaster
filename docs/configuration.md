# Configuration

Konfigurace se nacita z environment variables. Pro lokalni provoz zkopirujte `.env.example` do `.env`.

## Aplikace

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://ticketmaster:ticketmaster@db:5432/ticketmaster` | SQLAlchemy connection string |
| `APP_SECRET` | dev hodnota | podpis autentizacnich tokenu |
| `APP_BASE_URL` | `http://localhost:3006` | verejna adresa aplikace |
| `TICKETMASTER_DEV_PASSWORD` | `ChangeMe123!` | heslo pro dev partner uzivatele |
| `UPLOAD_DIR` | `/app/uploads` | uloziste priloh uvnitr API containeru |
| `WEB_CONCURRENCY` | `2` | pocet uvicorn worker procesu |

V produkci zmente `APP_SECRET`, `POSTGRES_PASSWORD`, `TRUSTED_HOSTS` a `CORS_ORIGINS`.

## PostgreSQL

| Promenna | Vychozi hodnota |
| --- | --- |
| `POSTGRES_DB` | `ticketmaster` |
| `POSTGRES_USER` | `ticketmaster` |
| `POSTGRES_PASSWORD` | `ticketmaster` |

## SMTP

| Promenna | Vychozi hodnota |
| --- | --- |
| `SMTP_HOST` | `mailpit` |
| `SMTP_PORT` | `1025` |
| `SMTP_USERNAME` | prazdne |
| `SMTP_PASSWORD` | prazdne |
| `SMTP_FROM` | `ticketmaster@example.test` |
| `SMTP_TLS` | `false` |
| `MAIL_SUPPRESS_SEND` | `false` |

## GitLab

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `GITLAB_BASE_URL` | `https://gitlab.example.test` | GitLab base URL |
| `GITLAB_PROJECT_ID` | `ticketmaster-dev-placeholder` | project ID/path pro L3 issue |
| `GITLAB_TOKEN` | prazdne | token pro realny GitLab |
| `GITLAB_DRY_RUN` | `true` | vytvari dry-run link bez volani GitLabu |

Bez GitLab issue nelze priradit ticket na L3 ani posunout L3 ticket do prace.

## Security a limity

| Promenna | Vychozi hodnota |
| --- | --- |
| `CORS_ORIGINS` | `*` |
| `TRUSTED_HOSTS` | `*` |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `10` |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `300` |
| `TICKET_PAGE_DEFAULT_LIMIT` | `50` |
| `TICKET_PAGE_MAX_LIMIT` | `200` |
| `EXPORT_TICKET_MAX_COUNT` | `2000` |
