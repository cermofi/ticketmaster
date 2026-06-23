from __future__ import annotations

from sqlalchemy.orm import Session

from ticketmaster.models import AuditLog, User
from ticketmaster.services.audit_context import is_audit_suppressed


def audit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor: User | None = None,
    source: str = "ui",
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> AuditLog | None:
    if is_audit_suppressed():
        return None
    row = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        changed_by_user_id=actor.id if actor else None,
        source=source,
    )
    db.add(row)
    return row
