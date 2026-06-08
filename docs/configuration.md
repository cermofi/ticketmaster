# Configuration

Konfigurace aplikace se nacita z `.env` a environment variables. Vychozi hodnoty jsou definovane v `backend/ticketmaster/core/config.py` a `docker-compose.yml`.

## Aplikacni hodnoty

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+psycopg2://...@pgbouncer:6432/ticketmaster` | SQLAlchemy connection string |
| `APP_SECRET` | dev hodnota | podpis tokenu, v produkci zmenit |
| `APP_BASE_URL` | `http://localhost:3006` | verejna adresa aplikace pro odkazy |
| `TICKETMASTER_DEV_PASSWORD` | `ChangeMe123!` | dev password vracene seed/pozvankami |
| `UPLOAD_DIR` | `/app/uploads` | cesta pro prilohy uvnitr containeru |
| `WEB_CONCURRENCY` | `2` | pocet API worker procesu |

## PostgreSQL

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `POSTGRES_DB` | `ticketmaster` | databaze |
| `POSTGRES_USER` | `ticketmaster` | DB uzivatel |
| `POSTGRES_PASSWORD` | `ticketmaster` | DB heslo |

V produkci zmenit `POSTGRES_PASSWORD` a ulozit ho mimo repozitar.

## pgBouncer

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `PGBOUNCER_MAX_CLIENT_CONN` | `500` | maximalni pocet klientskych spojeni |
| `PGBOUNCER_DEFAULT_POOL_SIZE` | `25` | defaultni pool size |
| `PGBOUNCER_RESERVE_POOL_SIZE` | `5` | rezervni pool |

pgBouncer bezi v transaction pooling rezimu a API pouziva pripojeni pres `pgbouncer:6432`.

## SMTP

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `SMTP_HOST` | `mailpit` | SMTP host |
| `SMTP_PORT` | `1025` | SMTP port |
| `SMTP_USERNAME` | prazdne | SMTP user |
| `SMTP_PASSWORD` | prazdne | SMTP password |
| `SMTP_FROM` | `ticketmaster@example.test` | odesilatel |
| `SMTP_TLS` | `false` | TLS pro SMTP |
| `MAIL_SUPPRESS_SEND` | `false` | potlaceni realneho odesilani |

## GitLab

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `GITLAB_BASE_URL` | `https://gitlab.example.test` | GitLab base URL |
| `GITLAB_PROJECT_ID` | placeholder | cilovy project ID/path |
| `GITLAB_TOKEN` | prazdne | private token |
| `GITLAB_DRY_RUN` | `true` | vytvari fake issue bez volani GitLabu |

## Security a request policy

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `CORS_ORIGINS` | `*` | povolene CORS originy |
| `TRUSTED_HOSTS` | `*` | povolene host headery |
| `LOGIN_RATE_LIMIT_ATTEMPTS` | `10` | pocet login pokusu |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `300` | okno rate limitu |

Produkce by nemela pouzivat `*`.

## Ticket pagination

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `TICKET_PAGE_DEFAULT_LIMIT` | `50` | default velikost stranky |
| `TICKET_PAGE_MAX_LIMIT` | `200` | maximalni velikost stranky |

## Redis a queue

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `REDIS_URL` | `redis://redis:6379/0` | Redis URL |
| `QUEUE_ENABLED` | `true` | povoli enqueue jobu |
| `QUEUE_NAME` | `ticketmaster:jobs` | Redis list s joby |
| `QUEUE_POLL_TIMEOUT_SECONDS` | `5` | BRPOP timeout |
| `WORKER_RETRY_INTERVAL_SECONDS` | `30` | perioda retry notifikaci |

## Sentry

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `SENTRY_DSN` | prazdne | DSN pro Sentry projekt |
| `SENTRY_ENVIRONMENT` | `production` | environment tag |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.05` | sampling tracingu |

Pokud `SENTRY_DSN` neni nastaveny, Sentry SDK se neinicializuje.

## Elasticsearch

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `ELASTICSEARCH_ENABLED` | `true` | povoli ES search |
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` | interni URL |
| `ELASTICSEARCH_INDEX` | `ticketmaster-tickets` | index |
| `ES_JAVA_OPTS` | `-Xms512m -Xmx512m` | JVM heap |

## ClamAV

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `CLAMAV_ENABLED` | `true` | povoli scan uploadu |
| `CLAMAV_HOST` | `clamav` | host |
| `CLAMAV_PORT` | `3310` | port clamd |
| `CLAMAV_TIMEOUT_SECONDS` | `30` | timeout scanu |

## Grafana

| Promenna | Vychozi hodnota | Popis |
| --- | --- | --- |
| `GRAFANA_ADMIN_USER` | `admin` | admin login |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | admin heslo |

V produkci zmenit heslo pred prvnim spustenim.

