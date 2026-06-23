from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.models import (
    Attachment,
    AuditLog,
    Client,
    Comment,
    CommentRevision,
    GitLabLink,
    Partner,
    Ticket,
    TicketParticipant,
    TicketWatcher,
    User,
)
from ticketmaster.services.internal_roles import get_internal_roles


def user_to_dict(user: User | None) -> dict | None:
    if user is None:
        return None
    internal_roles = get_internal_roles(user) if user.kind == "internal" else []
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "kind": user.kind,
        "internal_role": user.internal_role,
        "internal_roles": internal_roles,
        "partner_id": user.partner_id,
        "partner_role": user.partner_role,
        "active": user.active,
        "created_at": user.created_at,
    }


def partner_to_dict(partner: Partner) -> dict:
    return {"id": partner.id, "key": partner.key, "name": partner.name, "created_at": partner.created_at}


def client_to_dict(client: Client) -> dict:
    return {"id": client.id, "key": client.key, "partner_id": client.partner_id, "name": client.name, "created_at": client.created_at}


@dataclass(frozen=True)
class _TicketListContext:
    partners: dict[str, Partner]
    clients: dict[str, Client]
    users: dict[str, User]
    gitlab_links: dict[str, GitLabLink]


def _build_ticket_list_context(db: Session, tickets: Sequence[Ticket]) -> _TicketListContext:
    if not tickets:
        return _TicketListContext({}, {}, {}, {})
    ticket_ids = [ticket.id for ticket in tickets]
    partner_ids = {ticket.partner_id for ticket in tickets if ticket.partner_id}
    client_ids = {ticket.client_id for ticket in tickets if ticket.client_id}
    user_ids = {user_id for ticket in tickets for user_id in (ticket.owner_id, ticket.assignee_id) if user_id}
    partners = (
        {partner.id: partner for partner in db.scalars(select(Partner).where(Partner.id.in_(partner_ids))).all()}
        if partner_ids
        else {}
    )
    clients = (
        {client.id: client for client in db.scalars(select(Client).where(Client.id.in_(client_ids))).all()} if client_ids else {}
    )
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    gitlab_links = {
        link.ticket_id: link
        for link in db.scalars(
            select(GitLabLink).where(GitLabLink.ticket_id.in_(ticket_ids), GitLabLink.is_main.is_(True))
        ).all()
    }
    return _TicketListContext(partners=partners, clients=clients, users=users, gitlab_links=gitlab_links)


def _ticket_to_dict_with_context(
    ticket: Ticket,
    *,
    context: _TicketListContext,
    viewer: User | None = None,
    include_detail: bool = False,
    db: Session | None = None,
) -> dict:
    gitlab_link = context.gitlab_links.get(ticket.id)
    partner = context.partners.get(ticket.partner_id) if ticket.partner_id else None
    client = context.clients.get(ticket.client_id) if ticket.client_id else None
    owner = context.users.get(ticket.owner_id) if ticket.owner_id else None
    assignee = context.users.get(ticket.assignee_id) if ticket.assignee_id else None
    internal_viewer = viewer is None or viewer.kind == "internal"
    data = {
        "id": ticket.id,
        "internal": ticket.internal,
        "system": ticket.system,
        "kind": "system" if ticket.system else ("internal" if ticket.internal else "partner"),
        "partner_id": ticket.partner_id,
        "partner_name": partner.name if partner else None,
        "client_id": ticket.client_id,
        "client_name": client.name if client else None,
        "owner_id": ticket.owner_id,
        "owner_name": owner.name if owner else None,
        "created_by_id": ticket.created_by_id,
        "type": ticket.type,
        "priority": ticket.priority,
        "status": ticket.status,
        "resolver_team": ticket.resolver_team,
        "assignee_id": ticket.assignee_id,
        "assignee_name": assignee.name if assignee else None,
        "title": ticket.title,
        "description": ticket.description,
        "gitlab_status": gitlab_link.status if gitlab_link else None,
        "gitlab_issue_exists": gitlab_link is not None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }
    if internal_viewer:
        data["gitlab_link"] = gitlab_link.web_url if gitlab_link else None
        data["gitlab_issue_iid"] = gitlab_link.issue_iid if gitlab_link else None
    if include_detail:
        if db is None:
            raise ValueError("db session is required when include_detail=True")
        data["participants"] = [
            user_to_dict(user)
            for user in db.scalars(
                select(User).join(TicketParticipant, TicketParticipant.user_id == User.id).where(TicketParticipant.ticket_id == ticket.id)
            ).all()
        ]
        data["watchers"] = [
            user_to_dict(user)
            for user in db.scalars(select(User).join(TicketWatcher, TicketWatcher.user_id == User.id).where(TicketWatcher.ticket_id == ticket.id)).all()
        ]
    return data


def tickets_to_dict(db: Session, tickets: Sequence[Ticket], *, viewer: User | None = None, include_detail: bool = False) -> list[dict]:
    context = _build_ticket_list_context(db, tickets)
    return [
        _ticket_to_dict_with_context(ticket, context=context, viewer=viewer, include_detail=include_detail, db=db)
        for ticket in tickets
    ]


def ticket_to_dict(db: Session, ticket: Ticket, *, viewer: User | None = None, include_detail: bool = False) -> dict:
    gitlab_link = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id, GitLabLink.is_main.is_(True)))
    partner = db.get(Partner, ticket.partner_id) if ticket.partner_id else None
    client = db.get(Client, ticket.client_id) if ticket.client_id else None
    owner = db.get(User, ticket.owner_id) if ticket.owner_id else None
    assignee = db.get(User, ticket.assignee_id) if ticket.assignee_id else None
    internal_viewer = viewer is None or viewer.kind == "internal"
    data = {
        "id": ticket.id,
        "internal": ticket.internal,
        "system": ticket.system,
        "kind": "system" if ticket.system else ("internal" if ticket.internal else "partner"),
        "partner_id": ticket.partner_id,
        "partner_name": partner.name if partner else None,
        "client_id": ticket.client_id,
        "client_name": client.name if client else None,
        "owner_id": ticket.owner_id,
        "owner_name": owner.name if owner else None,
        "created_by_id": ticket.created_by_id,
        "type": ticket.type,
        "priority": ticket.priority,
        "status": ticket.status,
        "resolver_team": ticket.resolver_team,
        "assignee_id": ticket.assignee_id,
        "assignee_name": assignee.name if assignee else None,
        "title": ticket.title,
        "description": ticket.description,
        "gitlab_status": gitlab_link.status if gitlab_link else None,
        "gitlab_issue_exists": gitlab_link is not None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
    }
    if internal_viewer:
        data["gitlab_link"] = gitlab_link.web_url if gitlab_link else None
        data["gitlab_issue_iid"] = gitlab_link.issue_iid if gitlab_link else None
    if include_detail:
        data["participants"] = [
            user_to_dict(user)
            for user in db.scalars(
                select(User).join(TicketParticipant, TicketParticipant.user_id == User.id).where(TicketParticipant.ticket_id == ticket.id)
            ).all()
        ]
        data["watchers"] = [
            user_to_dict(user)
            for user in db.scalars(select(User).join(TicketWatcher, TicketWatcher.user_id == User.id).where(TicketWatcher.ticket_id == ticket.id)).all()
        ]
    return data


def comment_to_dict(comment: Comment, author: User | None = None) -> dict:
    return {
        "id": comment.id,
        "ticket_id": comment.ticket_id,
        "author_id": comment.author_id,
        "author_name": author.name if author else None,
        "visibility": comment.visibility,
        "body": None if comment.deleted_at else comment.body,
        "deleted": comment.deleted_at is not None,
        "edited_at": comment.edited_at,
        "created_at": comment.created_at,
    }


def comment_revision_to_dict(revision: CommentRevision) -> dict:
    return {
        "id": revision.id,
        "comment_id": revision.comment_id,
        "body": revision.body,
        "action": revision.action,
        "changed_by_user_id": revision.changed_by_user_id,
        "changed_at": revision.changed_at,
    }


def attachment_to_dict(attachment: Attachment, uploader: User | None = None) -> dict:
    return {
        "id": attachment.id,
        "ticket_id": attachment.ticket_id,
        "comment_id": attachment.comment_id,
        "uploaded_by_id": attachment.uploaded_by_id,
        "uploaded_by_name": uploader.name if uploader else None,
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "created_at": attachment.created_at,
        "download_url": f"/api/attachments/{attachment.id}/download",
    }


def audit_to_dict(row: AuditLog) -> dict:
    return {
        "id": row.id,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "action": row.action,
        "old_value": row.old_value,
        "new_value": row.new_value,
        "changed_by_user_id": row.changed_by_user_id,
        "source": row.source,
        "changed_at": row.changed_at,
    }
