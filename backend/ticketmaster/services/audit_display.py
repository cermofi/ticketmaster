from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.models import Attachment, AuditLog, Client, Comment, Partner, Ticket, User

AUDIT_DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"
AUDIT_DATETIME_TZ = ZoneInfo("Europe/Prague")

SOURCE_LABELS = {
    "system": "System",
    "cli": "System",
    "partner_api": "Partner API",
    "gitlab": "GitLab",
    "gitlab_webhook": "GitLab",
    "ui": "UI",
}


def format_audit_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(AUDIT_DATETIME_TZ).strftime(AUDIT_DATETIME_FORMAT)


def user_display_label(user: User | None) -> str | None:
    if user is None:
        return None
    name = (user.name or "").strip()
    email = (user.email or "").strip()
    if name and email and name.lower() != email.lower():
        return f"{name} ({email})"
    return name or email or None


def changed_by_display_label(db: Session, row: AuditLog, users_by_id: dict[str, User] | None = None) -> str:
    if row.changed_by_user_id:
        user = users_by_id.get(row.changed_by_user_id) if users_by_id is not None else db.get(User, row.changed_by_user_id)
        label = user_display_label(user)
        if label:
            return label
    source = (row.source or "").strip()
    if source in SOURCE_LABELS:
        return SOURCE_LABELS[source]
    if source:
        return source.replace("_", " ").title()
    return "Unknown"


def _truncate(text: str, length: int = 60) -> str:
    text = text.strip()
    if len(text) <= length:
        return text
    return f"{text[: length - 1]}…"


def _ticket_label(ticket: Ticket | None, ticket_id: str) -> str:
    if ticket is None:
        return f"Ticket {ticket_id[:8]}"
    title = _truncate(ticket.title, 50)
    return f"Ticket {ticket.id[:8]} · {title}"


def entity_display_label(
    db: Session,
    row: AuditLog,
    *,
    users_by_id: dict[str, User] | None = None,
    tickets_by_id: dict[str, Ticket] | None = None,
    partners_by_id: dict[str, Partner] | None = None,
    clients_by_id: dict[str, Client] | None = None,
    comments_by_id: dict[str, Comment] | None = None,
    attachments_by_id: dict[str, Attachment] | None = None,
) -> str:
    entity_type = row.entity_type
    entity_id = row.entity_id

    if entity_type == "User":
        user = users_by_id.get(entity_id) if users_by_id is not None else db.get(User, entity_id)
        return user_display_label(user) or f"User {entity_id[:8]}"

    if entity_type == "Ticket":
        ticket = tickets_by_id.get(entity_id) if tickets_by_id is not None else db.get(Ticket, entity_id)
        return _ticket_label(ticket, entity_id)

    if entity_type == "Partner":
        partner = partners_by_id.get(entity_id) if partners_by_id is not None else db.get(Partner, entity_id)
        if partner:
            return f"{partner.name} ({partner.key})"
        return f"Partner {entity_id[:8]}"

    if entity_type == "Client":
        client = clients_by_id.get(entity_id) if clients_by_id is not None else db.get(Client, entity_id)
        if client:
            return f"{client.name} ({client.key})"
        return f"Client {entity_id[:8]}"

    if entity_type == "Comment":
        comment = comments_by_id.get(entity_id) if comments_by_id is not None else db.get(Comment, entity_id)
        if comment:
            ticket = tickets_by_id.get(comment.ticket_id) if tickets_by_id is not None else db.get(Ticket, comment.ticket_id)
            ticket_part = ticket.id[:8] if ticket else comment.ticket_id[:8]
            return f"Comment on ticket {ticket_part}"
        return f"Comment {entity_id[:8]}"

    if entity_type == "Attachment":
        attachment = attachments_by_id.get(entity_id) if attachments_by_id is not None else db.get(Attachment, entity_id)
        if attachment:
            filename = _truncate(attachment.filename, 40)
            return f"Attachment {filename}"
        return f"Attachment {entity_id[:8]}"

    if entity_type == "Auth":
        if "@" in entity_id:
            return f"Auth {entity_id}"
        user = users_by_id.get(entity_id) if users_by_id is not None else db.get(User, entity_id)
        label = user_display_label(user)
        if label:
            return f"Auth {label}"
        return f"Auth {entity_id[:8]}"

    return f"{entity_type} {entity_id[:8]}"


def _load_related_maps(db: Session, rows: list[AuditLog]) -> dict[str, dict[str, object]]:
    user_ids: set[str] = set()
    ticket_ids: set[str] = set()
    partner_ids: set[str] = set()
    client_ids: set[str] = set()
    comment_ids: set[str] = set()
    attachment_ids: set[str] = set()

    for row in rows:
        if row.changed_by_user_id:
            user_ids.add(row.changed_by_user_id)
        if row.entity_type == "User":
            user_ids.add(row.entity_id)
        elif row.entity_type == "Ticket":
            ticket_ids.add(row.entity_id)
        elif row.entity_type == "Partner":
            partner_ids.add(row.entity_id)
        elif row.entity_type == "Client":
            client_ids.add(row.entity_id)
        elif row.entity_type == "Comment":
            comment_ids.add(row.entity_id)
        elif row.entity_type == "Attachment":
            attachment_ids.add(row.entity_id)
        elif row.entity_type == "Auth" and "@" not in row.entity_id:
            user_ids.add(row.entity_id)

    comments_by_id: dict[str, Comment] = {}
    if comment_ids:
        comments = list(db.scalars(select(Comment).where(Comment.id.in_(comment_ids))).all())
        comments_by_id = {comment.id: comment for comment in comments}
        ticket_ids.update(comment.ticket_id for comment in comments)

    attachments_by_id: dict[str, Attachment] = {}
    if attachment_ids:
        attachments = list(db.scalars(select(Attachment).where(Attachment.id.in_(attachment_ids))).all())
        attachments_by_id = {attachment.id: attachment for attachment in attachments}

    users_by_id = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    tickets_by_id = {ticket.id: ticket for ticket in db.scalars(select(Ticket).where(Ticket.id.in_(ticket_ids))).all()} if ticket_ids else {}
    partners_by_id = {partner.id: partner for partner in db.scalars(select(Partner).where(Partner.id.in_(partner_ids))).all()} if partner_ids else {}
    clients_by_id = {client.id: client for client in db.scalars(select(Client).where(Client.id.in_(client_ids))).all()} if client_ids else {}

    return {
        "users_by_id": users_by_id,
        "tickets_by_id": tickets_by_id,
        "partners_by_id": partners_by_id,
        "clients_by_id": clients_by_id,
        "comments_by_id": comments_by_id,
        "attachments_by_id": attachments_by_id,
    }


def enrich_audit_row(db: Session, row: AuditLog, related: dict[str, dict[str, object]]) -> dict:
    users_by_id = related["users_by_id"]
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "entity_label": entity_display_label(
            db,
            row,
            users_by_id=users_by_id,
            tickets_by_id=related["tickets_by_id"],
            partners_by_id=related["partners_by_id"],
            clients_by_id=related["clients_by_id"],
            comments_by_id=related["comments_by_id"],
            attachments_by_id=related["attachments_by_id"],
        ),
        "action": row.action,
        "old_value": row.old_value,
        "new_value": row.new_value,
        "changed_by_user_id": row.changed_by_user_id,
        "changed_by_label": changed_by_display_label(db, row, users_by_id=users_by_id),
        "source": row.source,
        "changed_at": row.changed_at,
        "changed_at_display": format_audit_datetime(row.changed_at),
    }


def enrich_audit_rows(db: Session, rows: list[AuditLog]) -> list[dict]:
    if not rows:
        return []
    related = _load_related_maps(db, rows)
    return [enrich_audit_row(db, row, related) for row in rows]
