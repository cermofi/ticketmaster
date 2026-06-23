from __future__ import annotations

from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ticketmaster.models import (
    Attachment,
    AuditLog,
    Client,
    ClientAssignment,
    Comment,
    CommentRevision,
    GitLabLink,
    GitLabSyncEvent,
    Notification,
    Partner,
    Ticket,
    TicketParticipant,
    TicketWatcher,
    User,
)

SMOKE_MARKER = "[SMOKE]"

SEED_TICKET_TITLES = frozenset(
    {
        "Seeded partner question",
        "Seeded system integration ticket",
    }
)

SEED_PARTNER_KEYS = frozenset({"acme-partner", "acme"})
SEED_CLIENT_KEYS = frozenset({"acme-partner-acme-bank", "acme-bank"})

SEED_USER_EMAILS = frozenset(
    {
        "dm@example.test",
        "l1@example.test",
        "l2@example.test",
        "l3@example.test",
        "responsible@acme.example",
        "technical@acme.example",
        "cli-system@ticketmaster.local",
    }
)

# Never auto-delete; may be repurposed as production admin after seed-dev.
PROTECTED_SEED_EMAILS = frozenset({"admin@example.test"})


def _ticket_smoke_filter(marker_only: bool):
    marker_clause = or_(Ticket.title.contains(SMOKE_MARKER), Ticket.description.contains(SMOKE_MARKER))
    if marker_only:
        return marker_clause
    return or_(
        marker_clause,
        Ticket.title.in_(SEED_TICKET_TITLES),
        Ticket.title.ilike("Assignee rule smoke"),
        Ticket.description.ilike("%seed-dev for%smoke%"),
        Ticket.description.ilike("%API smoke tests%"),
        Ticket.description.ilike("%API sanity%"),
    )


def find_smoke_ticket_ids(db: Session, *, marker_only: bool = True) -> list[str]:
    stmt = select(Ticket.id).where(_ticket_smoke_filter(marker_only))
    return list(db.scalars(stmt).all())


def find_seed_partner_ids(db: Session) -> list[str]:
    return list(db.scalars(select(Partner.id).where(Partner.key.in_(SEED_PARTNER_KEYS))).all())


def find_seed_client_ids(db: Session) -> list[str]:
    return list(db.scalars(select(Client.id).where(Client.key.in_(SEED_CLIENT_KEYS))).all())


def _user_has_ticket_references(db: Session, user_id: str) -> bool:
    ticket_ref = db.scalar(
        select(Ticket.id).where(
            or_(Ticket.created_by_id == user_id, Ticket.owner_id == user_id, Ticket.assignee_id == user_id)
        ).limit(1)
    )
    return ticket_ref is not None


def find_seed_user_ids(db: Session) -> list[str]:
    users = db.scalars(select(User).where(User.email.in_(SEED_USER_EMAILS))).all()
    return [user.id for user in users if not _user_has_ticket_references(db, user.id)]


def discover_smoke_artifacts(db: Session, *, marker_only: bool = True) -> dict[str, Any]:
    ticket_ids = find_smoke_ticket_ids(db, marker_only=marker_only)
    tickets = db.scalars(select(Ticket).where(Ticket.id.in_(ticket_ids)).order_by(Ticket.created_at)).all() if ticket_ids else []
    seed_partners = db.scalars(select(Partner).where(Partner.key.in_(SEED_PARTNER_KEYS))).all() if not marker_only else []
    seed_clients = db.scalars(select(Client).where(Client.key.in_(SEED_CLIENT_KEYS))).all() if not marker_only else []
    seed_users = (
        db.scalars(select(User).where(or_(User.email.in_(SEED_USER_EMAILS), User.email.in_(PROTECTED_SEED_EMAILS)))).all()
        if not marker_only
        else []
    )
    removable_user_ids = set(find_seed_user_ids(db)) if not marker_only else set()
    return {
        "marker_only": marker_only,
        "tickets": [{"id": row.id, "title": row.title} for row in tickets],
        "seed_partners": [{"id": row.id, "key": row.key, "name": row.name} for row in seed_partners],
        "seed_clients": [{"id": row.id, "key": row.key, "name": row.name} for row in seed_clients],
        "seed_users": [
            {
                "id": row.id,
                "email": row.email,
                "name": row.name,
                "removable": row.id in removable_user_ids,
            }
            for row in seed_users
        ],
    }


def _clear_user_references(db: Session, user_ids: list[str]) -> None:
    if not user_ids:
        return
    db.execute(delete(TicketParticipant).where(TicketParticipant.user_id.in_(user_ids)))
    db.execute(delete(TicketWatcher).where(TicketWatcher.user_id.in_(user_ids)))
    db.execute(delete(ClientAssignment).where(ClientAssignment.user_id.in_(user_ids)))
    for model, attr_name in [
        (Comment, "author_id"),
        (Comment, "changed_by_user_id"),
        (CommentRevision, "changed_by_user_id"),
        (Attachment, "uploaded_by_id"),
        (AuditLog, "changed_by_user_id"),
    ]:
        db.execute(update(model).where(getattr(model, attr_name).in_(user_ids)).values({attr_name: None}))
    db.flush()


def _partner_has_tickets(db: Session, partner_id: str) -> bool:
    return db.scalar(select(Ticket.id).where(Ticket.partner_id == partner_id).limit(1)) is not None


def _client_has_tickets(db: Session, client_id: str) -> bool:
    return db.scalar(select(Ticket.id).where(Ticket.client_id == client_id).limit(1)) is not None


def delete_tickets_cascade(
    db: Session,
    ticket_ids: list[str],
    *,
    preserve_audit_actions: frozenset[str] | None = None,
) -> dict[str, int]:
    if not ticket_ids:
        return {}

    comment_ids = list(db.scalars(select(Comment.id).where(Comment.ticket_id.in_(ticket_ids))).all())
    deleted: dict[str, int] = {}

    if comment_ids:
        deleted["comment_revisions"] = db.execute(
            delete(CommentRevision).where(CommentRevision.comment_id.in_(comment_ids))
        ).rowcount or 0

    deleted["attachments"] = db.execute(delete(Attachment).where(Attachment.ticket_id.in_(ticket_ids))).rowcount or 0

    if comment_ids:
        deleted["comments"] = db.execute(delete(Comment).where(Comment.id.in_(comment_ids))).rowcount or 0

    for table_name, model, column in [
        ("ticket_participants", TicketParticipant, TicketParticipant.ticket_id),
        ("ticket_watchers", TicketWatcher, TicketWatcher.ticket_id),
        ("gitlab_links", GitLabLink, GitLabLink.ticket_id),
        ("gitlab_sync_events", GitLabSyncEvent, GitLabSyncEvent.ticket_id),
        ("notifications", Notification, Notification.ticket_id),
    ]:
        deleted[table_name] = db.execute(delete(model).where(column.in_(ticket_ids))).rowcount or 0

    deleted["tickets"] = db.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids))).rowcount or 0

    entity_ids = ticket_ids + comment_ids
    audit_stmt = delete(AuditLog).where(
        or_(
            AuditLog.entity_id.in_(entity_ids),
            AuditLog.entity_id.in_(ticket_ids),
        )
    )
    if preserve_audit_actions:
        audit_stmt = audit_stmt.where(AuditLog.action.notin_(preserve_audit_actions))
    deleted["audit_logs"] = db.execute(audit_stmt).rowcount or 0

    db.flush()
    return deleted


def delete_seed_entities(db: Session) -> dict[str, int]:
    deleted: dict[str, int] = {}

    partner_ids = [partner_id for partner_id in find_seed_partner_ids(db) if not _partner_has_tickets(db, partner_id)]
    client_ids = [client_id for client_id in find_seed_client_ids(db) if not _client_has_tickets(db, client_id)]
    user_ids = find_seed_user_ids(db)

    if client_ids or user_ids:
        assignment_filters = []
        if client_ids:
            assignment_filters.append(ClientAssignment.client_id.in_(client_ids))
        if user_ids:
            assignment_filters.append(ClientAssignment.user_id.in_(user_ids))
        deleted["client_assignments"] = db.execute(
            delete(ClientAssignment).where(or_(*assignment_filters))
        ).rowcount or 0

    _clear_user_references(db, user_ids)

    if user_ids:
        seed_emails = list(db.scalars(select(User.email).where(User.id.in_(user_ids))).all())
        if seed_emails:
            deleted["notifications_users"] = db.execute(
                delete(Notification).where(Notification.recipient_email.in_(seed_emails))
            ).rowcount or 0

    all_entity_ids = partner_ids + client_ids + user_ids
    if all_entity_ids:
        deleted["audit_logs_seed"] = db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(all_entity_ids))).rowcount or 0
    if user_ids:
        deleted["audit_logs_seed"] = deleted.get("audit_logs_seed", 0) + (
            db.execute(delete(AuditLog).where(AuditLog.changed_by_user_id.in_(user_ids))).rowcount or 0
        )

    if client_ids:
        deleted["clients"] = db.execute(delete(Client).where(Client.id.in_(client_ids))).rowcount or 0

    if user_ids:
        deleted["users"] = db.execute(delete(User).where(User.id.in_(user_ids))).rowcount or 0

    if partner_ids:
        deleted["partners"] = db.execute(delete(Partner).where(Partner.id.in_(partner_ids))).rowcount or 0

    db.flush()
    return deleted


def cleanup_smoke_artifacts(db: Session, *, marker_only: bool = True, dry_run: bool = False) -> dict[str, Any]:
    discovery = discover_smoke_artifacts(db, marker_only=marker_only)
    if dry_run:
        return {"dry_run": True, "discovery": discovery, "deleted": {}}

    ticket_ids = [row["id"] for row in discovery["tickets"]]
    deleted = delete_tickets_cascade(db, ticket_ids)
    if not marker_only:
        for key, value in delete_seed_entities(db).items():
            deleted[key] = deleted.get(key, 0) + value

    return {"dry_run": False, "discovery": discovery, "deleted": deleted}


def sql_discovery_queries(marker_only: bool = True) -> str:
    marker_sql = (
        "SELECT id, title FROM tickets\n"
        f" WHERE title LIKE '%{SMOKE_MARKER}%' OR description LIKE '%{SMOKE_MARKER}%';\n"
    )
    if marker_only:
        return marker_sql
    return (
        marker_sql
        + "\n"
        + "SELECT id, title FROM tickets WHERE title IN ('Seeded partner question', 'Seeded system integration ticket')\n"
        + "   OR title ILIKE 'Assignee rule smoke'\n"
        + "   OR description ILIKE '%seed-dev for%smoke%'\n"
        + "   OR description ILIKE '%API smoke tests%'\n"
        + "   OR description ILIKE '%API sanity%';\n"
        + "\n"
        + "SELECT id, key, name FROM partners WHERE key IN ('acme-partner', 'acme');\n"
        + "SELECT id, key, name FROM clients WHERE key IN ('acme-partner-acme-bank', 'acme-bank');\n"
        + "SELECT id, email FROM users WHERE email IN (\n"
        + "  'dm@example.test', 'l1@example.test', 'l2@example.test', 'l3@example.test',\n"
        + "  'responsible@acme.example', 'technical@acme.example', 'cli-system@ticketmaster.local'\n"
        + ");\n"
        + "-- admin@example.test is reported but never auto-deleted (may be production admin).\n"
    )
