from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import String, and_, cast, or_, select
from sqlalchemy.orm import Session

from ticketmaster.models import AuditLog, User
from ticketmaster.services.audit_display import AUDIT_DATETIME_FORMAT, AUDIT_DATETIME_TZ

DEFAULT_AUDIT_LIMIT = 200
MAX_AUDIT_LIMIT = 200


def parse_audit_filter_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("empty datetime")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.strptime(raw, AUDIT_DATETIME_FORMAT)
        parsed = parsed.replace(tzinfo=AUDIT_DATETIME_TZ)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=AUDIT_DATETIME_TZ)
    return parsed.astimezone(timezone.utc)


def audit_filter_options(db: Session) -> dict[str, list[str]]:
    actions = list(db.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action)).all())
    sources = list(db.scalars(select(AuditLog.source).distinct().order_by(AuditLog.source)).all())
    entity_types = list(db.scalars(select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)).all())
    return {
        "actions": actions,
        "sources": sources,
        "entity_types": entity_types,
    }


def _changed_by_clause(changed_by: str):
    needle = f"%{changed_by.strip()}%"
    user_ids = select(User.id).where(or_(User.name.ilike(needle), User.email.ilike(needle)))
    return AuditLog.changed_by_user_id.in_(user_ids)


def _search_clause(db: Session, search: str):
    needle = f"%{search.strip()}%"
    clauses = [
        AuditLog.entity_id.ilike(needle),
        AuditLog.action.ilike(needle),
        AuditLog.entity_type.ilike(needle),
        AuditLog.source.ilike(needle),
    ]
    user_ids = select(User.id).where(or_(User.name.ilike(needle), User.email.ilike(needle)))
    clauses.append(AuditLog.changed_by_user_id.in_(user_ids))

    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"
    if dialect == "postgresql":
        clauses.extend(
            [
                cast(AuditLog.old_value, String).ilike(needle),
                cast(AuditLog.new_value, String).ilike(needle),
            ]
        )
    else:
        clauses.extend(
            [
                cast(AuditLog.old_value, String).ilike(needle),
                cast(AuditLog.new_value, String).ilike(needle),
            ]
        )
    return or_(*clauses)


def _has_details_clause(db: Session, *, has_details: bool):
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"

    def _column_has_payload(column):
        if dialect == "postgresql":
            return column.is_not(None)
        return and_(column.is_not(None), cast(column, String) != "null")

    has_payload = or_(_column_has_payload(AuditLog.old_value), _column_has_payload(AuditLog.new_value))
    if has_details:
        return has_payload
    return ~has_payload


def build_audit_list_stmt(
    db: Session,
    *,
    entity_id: str | None = None,
    changed_from: datetime | None = None,
    changed_to: datetime | None = None,
    action: str | None = None,
    source: str | None = None,
    entity_type: str | None = None,
    changed_by: str | None = None,
    search: str | None = None,
    has_details: bool | None = None,
):
    stmt = select(AuditLog)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id.strip())
    if changed_from is not None:
        stmt = stmt.where(AuditLog.changed_at >= changed_from)
    if changed_to is not None:
        stmt = stmt.where(AuditLog.changed_at <= changed_to)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action.strip()}%"))
    if source:
        stmt = stmt.where(AuditLog.source == source.strip())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type.strip())
    if changed_by:
        stmt = stmt.where(_changed_by_clause(changed_by))
    if search:
        stmt = stmt.where(_search_clause(db, search))
    if has_details is not None:
        stmt = stmt.where(_has_details_clause(db, has_details=has_details))
    return stmt


def list_audit_logs(
    db: Session,
    *,
    entity_id: str | None = None,
    changed_from: datetime | None = None,
    changed_to: datetime | None = None,
    action: str | None = None,
    source: str | None = None,
    entity_type: str | None = None,
    changed_by: str | None = None,
    search: str | None = None,
    has_details: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[AuditLog]:
    actual_limit = min(max(limit or DEFAULT_AUDIT_LIMIT, 1), MAX_AUDIT_LIMIT)
    actual_offset = max(offset, 0)
    stmt = build_audit_list_stmt(
        db,
        entity_id=entity_id,
        changed_from=changed_from,
        changed_to=changed_to,
        action=action,
        source=source,
        entity_type=entity_type,
        changed_by=changed_by,
        search=search,
        has_details=has_details,
    )
    stmt = stmt.order_by(AuditLog.changed_at.desc()).limit(actual_limit).offset(actual_offset)
    return list(db.scalars(stmt).all())
