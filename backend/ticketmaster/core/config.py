from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    candidates = [Path.cwd() / ".env", Path.cwd().parent / ".env"]
    for path in candidates:
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        break


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ticketmaster:ticketmaster@db:5432/ticketmaster",
    )
    app_secret: str = os.getenv("APP_SECRET", "dev-change-me")
    base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8080")
    dev_password: str = os.getenv("TICKETMASTER_DEV_PASSWORD", "ChangeMe123!")

    smtp_host: str = os.getenv("SMTP_HOST", "mailpit")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME") or None
    smtp_password: str | None = os.getenv("SMTP_PASSWORD") or None
    smtp_from: str = os.getenv("SMTP_FROM", "ticketmaster@example.test")
    smtp_tls: bool = _bool("SMTP_TLS", False)
    mail_suppress_send: bool = _bool("MAIL_SUPPRESS_SEND", False)

    gitlab_base_url: str = os.getenv("GITLAB_BASE_URL", "https://gitlab.teskalabs.int")
    gitlab_token: str | None = os.getenv("GITLAB_TOKEN") or None
    gitlab_project_id: str | None = os.getenv("GITLAB_PROJECT_ID", "503") or None
    gitlab_dry_run: bool = _bool("GITLAB_DRY_RUN", True)

    upload_dir: str = os.getenv("UPLOAD_DIR", "/app/uploads")

    cors_origins: tuple[str, ...] = tuple(origin.strip() for origin in os.getenv("CORS_ORIGINS", "*").split(",") if origin.strip())
    trusted_hosts: tuple[str, ...] = tuple(host.strip() for host in os.getenv("TRUSTED_HOSTS", "*").split(",") if host.strip())
    login_rate_limit_attempts: int = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "10"))
    login_rate_limit_window_seconds: int = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))
    ticket_page_default_limit: int = int(os.getenv("TICKET_PAGE_DEFAULT_LIMIT", "50"))
    ticket_page_max_limit: int = int(os.getenv("TICKET_PAGE_MAX_LIMIT", "200"))
    export_ticket_max_count: int = int(os.getenv("EXPORT_TICKET_MAX_COUNT", "2000"))
    allow_seed_dev: bool = _bool("ALLOW_SEED_DEV", "localhost" in os.getenv("APP_BASE_URL", "http://localhost:3006"))


settings = Settings()
