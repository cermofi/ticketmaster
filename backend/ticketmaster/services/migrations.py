from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

RISKY_SQL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bALTER\s+COLUMN\b.+\bTYPE\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class MigrationPlan:
    pending: list[str]
    risky_pending: list[str]

    @property
    def has_risky(self) -> bool:
        return bool(self.risky_pending)


def is_risky_migration_sql(sql: str) -> bool:
    return any(pattern.search(sql) for pattern in RISKY_SQL_PATTERNS)


def is_risky_migration(path: Path) -> bool:
    return is_risky_migration_sql(path.read_text(encoding="utf-8"))


def list_pending_migrations(engine: Engine) -> list[str]:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(200) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        existing = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
    return [path.name for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.name not in existing]


def plan_migrations(engine: Engine) -> MigrationPlan:
    pending = list_pending_migrations(engine)
    risky = [name for name in pending if is_risky_migration(MIGRATIONS_DIR / name)]
    return MigrationPlan(pending=pending, risky_pending=risky)


def run_migrations(engine: Engine, *, versions: list[str] | None = None) -> list[str]:
    applied: list[str] = []
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(200) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
        )
        existing = {row[0] for row in conn.execute(text("SELECT version FROM schema_migrations"))}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in existing:
                continue
            if versions is not None and path.name not in versions:
                continue
            conn.exec_driver_sql(path.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:version)"), {"version": path.name})
            applied.append(path.name)
    return applied


def write_rollback_artifact(
    *,
    deploy_dir: Path,
    pre_deploy_rev: str,
    backup_path: Path | None,
    risky_pending: list[str],
) -> Path:
    deploy_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact = deploy_dir / f"rollback-{stamp}.md"
    lines = [
        "# TicketMaster deploy rollback",
        "",
        f"- Saved git revision: `{pre_deploy_rev}`",
        f"- Risky migrations in this deploy: {', '.join(risky_pending) if risky_pending else 'none'}",
        f"- Pre-migrate backup: `{backup_path}`" if backup_path else "- Pre-migrate backup: not created",
        "",
        "## Roll back application",
        "",
        "```bash",
        "cd /home/new-ticketmaster",
        f"git checkout {pre_deploy_rev}",
        "docker compose up -d --build",
        "docker compose exec -T api ticketmaster-cli db migrate",
        "curl -fsS https://ticketmaster.cermofi.cz/api/ready",
        "./scripts/post-deploy-smoke.sh",
        "```",
        "",
        "## Restore database (only if risky migration ran)",
        "",
        "If a risky migration already applied and cannot be reversed by checkout:",
        "",
        "```bash",
        f"docker compose exec -T db psql -U \"$POSTGRES_USER\" \"$POSTGRES_DB\" < {backup_path or 'backup-YYYY-MM-DD.sql'}",
        "```",
        "",
    ]
    artifact.write_text("\n".join(lines), encoding="utf-8")
    return artifact
