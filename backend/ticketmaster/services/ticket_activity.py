from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ticketmaster.models import Attachment, AuditLog, Comment, Ticket, User

INTERNAL_ONLY_ACTIONS = frozenset({"internal_note.create"})

SOURCE_LABELS = {
    "system": "System",
    "cli": "System",
    "partner_api": "Partner API",
    "gitlab": "GitLab",
}


def _actor_label(db: Session, row: AuditLog) -> str:
    if row.changed_by_user_id:
        user = db.get(User, row.changed_by_user_id)
        if user and user.name:
            return user.name
    source = (row.source or "").strip()
    if source in SOURCE_LABELS:
        return SOURCE_LABELS[source]
    if source:
        return source.replace("_", " ").title()
    return "Unknown"


def _user_name(db: Session, user_id: str | None) -> str | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user.name if user else None


def _activity_title(db: Session, row: AuditLog) -> str:
    action = row.action
    new_value = row.new_value or {}
    old_value = row.old_value or {}

    if action in {"ticket.create", "ticket.create_internal", "ticket.create_system"}:
        return "Ticket created"
    if action in {"ticket.status_change", "ticket.status_auto_return"}:
        status = new_value.get("status")
        return f"Status set to {status}" if status else "Status changed"
    if action == "ticket.assign":
        assignee_name = _user_name(db, new_value.get("assignee_id"))
        team = new_value.get("resolver_team")
        if assignee_name:
            team_part = f" · {team}" if team else ""
            return f"Assigned to {assignee_name}{team_part}"
        if team:
            return f"Assigned to {team} queue"
        return "Assignment updated"
    if action == "ticket.unassign":
        return "Returned to queue"
    if action == "ticket.priority_change":
        priority = new_value.get("priority")
        return f"Priority set to {priority}" if priority else "Priority changed"
    if action == "ticket.type_change":
        ticket_type = new_value.get("type")
        return f"Type set to {ticket_type}" if ticket_type else "Type changed"
    if action == "ticket.close":
        return "Ticket closed"
    if action == "ticket.transfer_owner":
        owner_name = _user_name(db, new_value.get("owner_id"))
        return f"Owner changed to {owner_name}" if owner_name else "Owner changed"
    if action == "comment.create":
        return "Comment added"
    if action == "internal_note.create":
        return "Internal note added"
    if action == "participant.add":
        user_name = _user_name(db, new_value.get("user_id"))
        return f"Participant added: {user_name}" if user_name else "Participant added"
    if action == "participant.remove":
        user_name = _user_name(db, old_value.get("user_id"))
        return f"Participant removed: {user_name}" if user_name else "Participant removed"
    if action == "gitlab.create_issue":
        return "GitLab issue created"
    if action == "gitlab.sync_status":
        status = new_value.get("status")
        return f"GitLab status synced to {status}" if status else "GitLab status synced"
    if action == "gitlab.create_issue.error":
        return "GitLab issue creation failed"
    if action == "attachment.upload":
        filename = new_value.get("filename")
        return f"Attachment uploaded: {filename}" if filename else "Attachment uploaded"
    return action.replace(".", " ").replace("_", " ").title()


def _activity_filters(db: Session, ticket: Ticket) -> list:
    comment_ids = list(db.scalars(select(Comment.id).where(Comment.ticket_id == ticket.id)).all())
    attachment_ids = list(db.scalars(select(Attachment.id).where(Attachment.ticket_id == ticket.id)).all())

    filters = [(AuditLog.entity_type == "Ticket") & (AuditLog.entity_id == ticket.id)]
    if comment_ids:
        filters.append((AuditLog.entity_type == "Comment") & (AuditLog.entity_id.in_(comment_ids)))
    if attachment_ids:
        filters.append((AuditLog.entity_type == "Attachment") & (AuditLog.entity_id.in_(attachment_ids)))
    return filters


def ticket_activity(db: Session, *, ticket: Ticket, viewer: User, limit: int | None = None) -> list[dict]:
    filters = _activity_filters(db, ticket)
    if not filters:
        return []

    stmt = select(AuditLog).where(or_(*filters))
    if viewer.kind != "internal":
        stmt = stmt.where(AuditLog.action.not_in(tuple(INTERNAL_ONLY_ACTIONS)))
    stmt = stmt.order_by(AuditLog.changed_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)

    return [
        {
            "id": row.id,
            "action": row.action,
            "title": _activity_title(db, row),
            "author": _actor_label(db, row),
            "changed_by_user_id": row.changed_by_user_id,
            "source": row.source,
            "time": row.changed_at,
        }
        for row in db.scalars(stmt).all()
    ]
