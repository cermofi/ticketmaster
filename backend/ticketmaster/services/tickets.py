from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from ticketmaster.models import (
    Client,
    ClientAssignment,
    Comment,
    CommentRevision,
    Attachment,
    GitLabLink,
    Partner,
    Ticket,
    TicketParticipant,
    TicketWatcher,
    User,
)
from ticketmaster.models.constants import PRIORITIES, RESOLVER_TEAMS, STATUSES, TICKET_TYPES, WORKFLOW_TRANSITIONS
from ticketmaster.models.entities import new_id
from ticketmaster.services import gitlab, search as ticket_search
from ticketmaster.services.audit import audit
from ticketmaster.services.admin import resolve_client, resolve_user
from ticketmaster.services.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError
from ticketmaster.services.notifications import queue_email, queue_ticket_watchers


def validate_ticket_type(ticket_type: str) -> None:
    if ticket_type not in TICKET_TYPES:
        raise ValidationError(f"Unsupported ticket type: {ticket_type}")


def validate_priority(priority: str) -> None:
    if priority not in PRIORITIES:
        raise ValidationError(f"Unsupported priority: {priority}")


def get_ticket(db: Session, ticket_id: str) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise NotFoundError("Ticket not found")
    return ticket


def can_view_ticket(db: Session, user: User, ticket: Ticket) -> bool:
    if ticket.owner_id == user.id:
        return True
    if user.kind == "internal":
        if user.internal_role in {"Admin", "DeliveryManager"}:
            return True
        if user.internal_role in RESOLVER_TEAMS:
            if ticket.resolver_team == user.internal_role:
                return True
            if ticket.assignee_id:
                assignee = db.get(User, ticket.assignee_id)
                return bool(assignee and assignee.internal_role == user.internal_role)
        return False
    if ticket.internal:
        return False
    return ticket.partner_id == user.partner_id


def require_view(db: Session, user: User, ticket: Ticket) -> None:
    if not can_view_ticket(db, user, ticket):
        raise PermissionDenied("You are not allowed to view this ticket")


def can_comment(db: Session, user: User, ticket: Ticket) -> bool:
    if ticket.status == "Closed":
        raise ValidationError("Closed tickets cannot be commented")
    if user.kind == "internal":
        return can_view_ticket(db, user, ticket)
    if not can_view_ticket(db, user, ticket):
        return False
    return db.scalar(select(TicketParticipant).where(TicketParticipant.ticket_id == ticket.id, TicketParticipant.user_id == user.id)) is not None


def _add_participant_if_missing(db: Session, ticket_id: str, user_id: str) -> None:
    if not db.scalar(select(TicketParticipant).where(TicketParticipant.ticket_id == ticket_id, TicketParticipant.user_id == user_id)):
        db.add(TicketParticipant(id=new_id(), ticket_id=ticket_id, user_id=user_id))
    _add_watcher_if_missing(db, ticket_id, user_id)


def _add_watcher_if_missing(db: Session, ticket_id: str, user_id: str) -> None:
    if not db.scalar(select(TicketWatcher).where(TicketWatcher.ticket_id == ticket_id, TicketWatcher.user_id == user_id)):
        db.add(TicketWatcher(id=new_id(), ticket_id=ticket_id, user_id=user_id))


def create_partner_ticket(
    db: Session,
    *,
    actor: User,
    ticket_type: str,
    priority: str,
    title: str,
    description: str,
    client_id: str | None = None,
    participant_ids: list[str] | None = None,
    source: str = "ui",
) -> Ticket:
    if actor.kind != "partner" or actor.partner_role != "responsible":
        raise PermissionDenied("Only responsible partner users can create partner tickets")
    validate_ticket_type(ticket_type)
    validate_priority(priority)
    actual_priority = "Critical" if ticket_type == "Security Issue" and priority == "Normal" else priority
    client = None
    if client_id:
        client = resolve_client(db, client_id)
        if not client.active:
            raise ValidationError("Client must be active")
        if client.partner_id != actor.partner_id:
            raise ValidationError("Client must belong to the ticket owner's partner")
        assignment = db.scalar(select(ClientAssignment).where(ClientAssignment.client_id == client.id, ClientAssignment.user_id == actor.id))
        if not assignment:
            raise ValidationError("Ticket owner must be assigned as responsible person for the selected client")
    ticket = Ticket(
        id=new_id(),
        partner_id=actor.partner_id,
        client_id=client.id if client else None,
        owner_id=actor.id,
        created_by_id=actor.id,
        internal=False,
        type=ticket_type,
        priority=actual_priority,
        status="New",
        title=title,
        description=description,
    )
    db.add(ticket)
    db.flush()
    _add_participant_if_missing(db, ticket.id, actor.id)
    for user_id in participant_ids or []:
        user = db.get(User, user_id)
        if not user or user.kind != "partner" or user.partner_id != actor.partner_id or not user.active:
            raise ValidationError("Participants must be active users from the same partner")
        _add_participant_if_missing(db, ticket.id, user.id)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.create", actor=actor, source=source, new_value={"status": ticket.status, "partner_id": actor.partner_id})
    _notify_delivery_managers(db, ticket, "New TicketMaster ticket", f"New ticket created: {ticket.title}")
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def create_internal_ticket(
    db: Session,
    *,
    actor: User,
    ticket_type: str,
    priority: str,
    title: str,
    description: str,
    team: str | None = None,
    source: str = "ui",
) -> Ticket:
    if actor.kind != "internal" or actor.internal_role not in {"Admin", "DeliveryManager", "L1", "L2", "L3"}:
        raise PermissionDenied("Only internal users can create internal tickets")
    validate_ticket_type(ticket_type)
    validate_priority(priority)
    if team and team not in RESOLVER_TEAMS:
        raise ValidationError("Invalid resolver team")
    ticket = Ticket(
        id=new_id(),
        owner_id=actor.id,
        created_by_id=actor.id,
        internal=True,
        type=ticket_type,
        priority=priority,
        status="Assigned" if team else "New",
        resolver_team=team,
        title=title,
        description=description,
    )
    db.add(ticket)
    db.flush()
    _add_watcher_if_missing(db, ticket.id, actor.id)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.create_internal", actor=actor, source=source, new_value={"team": team, "status": ticket.status})
    if team == "L3":
        _ensure_l3_issue(db, ticket, actor, source)
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def list_visible_tickets(
    db: Session,
    *,
    actor: User,
    search: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    resolver_team: str | None = None,
    partner_id: str | None = None,
    internal: bool | None = None,
) -> list[Ticket]:
    stmt = _visible_ticket_stmt(
        db=db,
        actor=actor,
        search=search,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        resolver_team=resolver_team,
        partner_id=partner_id,
        internal=internal,
    ).order_by(Ticket.created_at.desc())
    return list(db.scalars(stmt).all())


def list_visible_tickets_page(
    db: Session,
    *,
    actor: User,
    search: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    resolver_team: str | None = None,
    partner_id: str | None = None,
    internal: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    base_stmt = _visible_ticket_stmt(
        db=db,
        actor=actor,
        search=search,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        resolver_team=resolver_team,
        partner_id=partner_id,
        internal=internal,
    )
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    rows = list(db.scalars(base_stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)).all())
    return rows, total


def _visible_ticket_stmt(
    *,
    db: Session,
    actor: User,
    search: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    ticket_type: str | None = None,
    resolver_team: str | None = None,
    partner_id: str | None = None,
    internal: bool | None = None,
):
    stmt = select(Ticket)
    if actor.kind == "partner":
        stmt = stmt.where(Ticket.internal.is_(False), Ticket.partner_id == actor.partner_id)
    elif actor.internal_role not in {"Admin", "DeliveryManager"}:
        stmt = stmt.where(or_(Ticket.resolver_team == actor.internal_role, Ticket.assignee_id == actor.id, Ticket.owner_id == actor.id))
    if search:
        search_ids = ticket_search.find_ticket_ids(search)
        if search_ids is not None:
            stmt = stmt.where(Ticket.id.in_(search_ids) if search_ids else false())
        elif db.bind and db.bind.dialect.name == "postgresql":
            query = func.plainto_tsquery("simple", search)
            ticket_vector = func.to_tsvector("simple", func.concat(func.coalesce(Ticket.title, ""), " ", func.coalesce(Ticket.description, "")))
            comment_vector = func.to_tsvector("simple", func.coalesce(Comment.body, ""))
            comment_match = (
                select(Comment.id)
                .where(
                    Comment.ticket_id == Ticket.id,
                    Comment.deleted_at.is_(None),
                    Comment.visibility == "comment",
                    comment_vector.op("@@")(query),
                )
                .exists()
            )
            stmt = stmt.where(or_(Ticket.id.ilike(f"%{search}%"), ticket_vector.op("@@")(query), comment_match))
        else:
            like = f"%{search}%"
            stmt = stmt.where(or_(Ticket.id.ilike(like), Ticket.title.ilike(like), Ticket.description.ilike(like)))
    if status:
        stmt = stmt.where(Ticket.status == status)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if ticket_type:
        stmt = stmt.where(Ticket.type == ticket_type)
    if resolver_team:
        stmt = stmt.where(Ticket.resolver_team == resolver_team)
    if partner_id:
        stmt = stmt.where(Ticket.partner_id == partner_id)
    if internal is not None:
        stmt = stmt.where(Ticket.internal.is_(internal))
    return stmt


def add_comment(db: Session, *, ticket: Ticket, actor: User, body: str, source: str = "ui") -> Comment:
    if not can_comment(db, actor, ticket):
        raise PermissionDenied("Only ticket communication participants can comment")
    comment = Comment(id=new_id(), ticket_id=ticket.id, author_id=actor.id, visibility="comment", body=body)
    db.add(comment)
    db.flush()
    audit(db, entity_type="Comment", entity_id=comment.id, action="comment.create", actor=actor, source=source, new_value={"ticket_id": ticket.id})
    queue_ticket_watchers(db, ticket_id=ticket.id, event="comment_created", subject=f"New comment on {ticket.title}", body=body)
    ticket_search.enqueue_ticket_index(ticket.id)
    return comment


def add_internal_note(db: Session, *, ticket: Ticket, actor: User, body: str, source: str = "ui") -> Comment:
    if ticket.status == "Closed":
        raise ValidationError("Closed tickets cannot be commented")
    if actor.kind != "internal" or not can_view_ticket(db, actor, ticket):
        raise PermissionDenied("Only internal users who can view the ticket can add internal notes")
    comment = Comment(id=new_id(), ticket_id=ticket.id, author_id=actor.id, visibility="internal_note", body=body)
    db.add(comment)
    db.flush()
    audit(db, entity_type="Comment", entity_id=comment.id, action="internal_note.create", actor=actor, source=source, new_value={"ticket_id": ticket.id})
    ticket_search.enqueue_ticket_index(ticket.id)
    return comment


def add_participant(db: Session, *, ticket: Ticket, actor: User, user_id: str, source: str = "ui") -> None:
    _require_participant_management(ticket, actor)
    user = db.get(User, user_id)
    if not user or user.kind != "partner" or user.partner_id != ticket.partner_id:
        raise ValidationError("Participant must be a user from the ticket partner")
    _add_participant_if_missing(db, ticket.id, user.id)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="participant.add", actor=actor, source=source, new_value={"user_id": user.id})
    queue_email(db, event="participant_added", recipient_email=user.email, subject=f"Added to ticket {ticket.title}", body=f"You were added to ticket {ticket.id}", ticket_id=ticket.id)
    ticket_search.enqueue_ticket_index(ticket.id)


def remove_participant(db: Session, *, ticket: Ticket, actor: User, user_id: str, source: str = "ui") -> None:
    _require_participant_management(ticket, actor)
    if ticket.owner_id == user_id:
        raise ValidationError("Ticket owner cannot be removed from participants")
    participant = db.scalar(select(TicketParticipant).where(TicketParticipant.ticket_id == ticket.id, TicketParticipant.user_id == user_id))
    if not participant:
        raise NotFoundError("Participant not found")
    watcher = db.scalar(select(TicketWatcher).where(TicketWatcher.ticket_id == ticket.id, TicketWatcher.user_id == user_id))
    db.delete(participant)
    if watcher:
        db.delete(watcher)
    ticket.updated_at = datetime.now(timezone.utc)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="participant.remove", actor=actor, source=source, old_value={"user_id": user_id})
    ticket_search.enqueue_ticket_index(ticket.id)


def assign_ticket(
    db: Session,
    *,
    ticket: Ticket,
    actor: User | None,
    team: str,
    assignee_ref: str | None = None,
    source: str = "ui",
) -> Ticket:
    if ticket.status == "Closed":
        raise ValidationError("Closed tickets cannot be assigned")
    if team not in RESOLVER_TEAMS:
        raise ValidationError("Invalid resolver team")
    if actor:
        _require_assign_permission(actor, ticket, team)
    assignee = None
    if assignee_ref:
        assignee = resolve_user(db, assignee_ref)
        if assignee.kind != "internal" or assignee.internal_role != team:
            raise ValidationError("Assignee must be an active internal user from the resolver team")
        _add_watcher_if_missing(db, ticket.id, assignee.id)
    old = {"status": ticket.status, "resolver_team": ticket.resolver_team, "assignee_id": ticket.assignee_id}
    ticket.status = "Assigned"
    ticket.resolver_team = team
    ticket.assignee_id = assignee.id if assignee else None
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.assign", actor=actor, source=source, old_value=old, new_value={"status": ticket.status, "resolver_team": team, "assignee_id": ticket.assignee_id})
    queue_ticket_watchers(db, ticket_id=ticket.id, event="ticket_assigned", subject=f"Ticket assigned: {ticket.title}", body=f"Ticket {ticket.id} was assigned to {team}.")
    if team == "L3":
        _ensure_l3_issue(db, ticket, actor, source)
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def transition_ticket(db: Session, *, ticket: Ticket, actor: User, new_status: str, source: str = "ui") -> Ticket:
    validate_transition(db, ticket=ticket, actor=actor, new_status=new_status)
    old = {"status": ticket.status}
    ticket.status = new_status
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.status_change", actor=actor, source=source, old_value=old, new_value={"status": new_status})
    queue_ticket_watchers(db, ticket_id=ticket.id, event="status_changed", subject=f"Ticket status changed: {ticket.title}", body=f"Ticket {ticket.id} is now {new_status}.")
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def validate_transition(db: Session, *, ticket: Ticket, actor: User, new_status: str) -> None:
    if new_status not in STATUSES:
        raise ValidationError("Invalid ticket status")
    if new_status not in WORKFLOW_TRANSITIONS[ticket.status]:
        raise ValidationError(f"Transition {ticket.status} -> {new_status} is not allowed")
    _require_transition_permission(actor, ticket, new_status)
    if new_status == "Assigned" and not ticket.resolver_team:
        raise ValidationError("Assigned tickets must have resolver_team")
    if new_status == "In progress" and ticket.resolver_team == "L3":
        link = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id, GitLabLink.is_main.is_(True)))
        if not link and not ticket.gitlab_error_overridden:
            raise ConflictError("L3 ticket cannot move to In progress without a GitLab issue")


def available_transitions(db: Session, *, ticket: Ticket, actor: User) -> list[str]:
    allowed = []
    for status in sorted(WORKFLOW_TRANSITIONS[ticket.status]):
        try:
            validate_transition(db, ticket=ticket, actor=actor, new_status=status)
        except (ConflictError, PermissionDenied, ValidationError):
            continue
        allowed.append(status)
    return allowed


def close_ticket(db: Session, *, ticket: Ticket, actor: User | None, source: str = "ui") -> Ticket:
    if actor and actor.kind == "partner":
        raise PermissionDenied("Partner users cannot close tickets")
    if ticket.status != "Closed":
        if ticket.status not in {"Resolved", "Rejected", "Duplicate", "Cancelled"}:
            if actor and actor.internal_role not in {"Admin", "DeliveryManager"}:
                raise ValidationError("Ticket can be closed from Resolved, Rejected, Duplicate or Cancelled")
        old = {"status": ticket.status}
        ticket.status = "Closed"
        ticket.updated_at = datetime.now(timezone.utc)
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.close", actor=actor, source=source, old_value=old, new_value={"status": "Closed"})
        queue_ticket_watchers(db, ticket_id=ticket.id, event="ticket_closed", subject=f"Ticket closed: {ticket.title}", body=f"Ticket {ticket.id} was closed.")
        ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def transfer_owner(db: Session, *, ticket: Ticket, actor: User | None, new_owner_ref: str, source: str = "ui") -> Ticket:
    if ticket.internal:
        raise ValidationError("Internal tickets do not have partner owners")
    if actor:
        allowed = actor.kind == "internal" and actor.internal_role in {"Admin", "DeliveryManager"}
        allowed = allowed or (actor.kind == "partner" and ticket.owner_id == actor.id)
        if not allowed:
            raise PermissionDenied("You are not allowed to transfer this ticket")
    new_owner = resolve_user(db, new_owner_ref)
    if new_owner.kind != "partner" or new_owner.partner_role != "responsible" or new_owner.partner_id != ticket.partner_id:
        raise ValidationError("New owner must be a responsible user from the same partner")
    if ticket.client_id:
        assignment = db.scalar(select(ClientAssignment).where(ClientAssignment.client_id == ticket.client_id, ClientAssignment.user_id == new_owner.id))
        if not assignment:
            raise ValidationError("New owner must be assigned as responsible person for the ticket client")
    old = {"owner_id": ticket.owner_id}
    ticket.owner_id = new_owner.id
    ticket.updated_at = datetime.now(timezone.utc)
    _add_participant_if_missing(db, ticket.id, new_owner.id)
    db.flush()
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.transfer_owner", actor=actor, source=source, old_value=old, new_value={"owner_id": new_owner.id})
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def visible_comments(db: Session, *, ticket: Ticket, actor: User) -> list[Comment]:
    require_view(db, actor, ticket)
    stmt = select(Comment).where(Comment.ticket_id == ticket.id, Comment.deleted_at.is_(None))
    if actor.kind == "partner":
        stmt = stmt.where(Comment.visibility == "comment")
    stmt = stmt.order_by(Comment.created_at.asc())
    return list(db.scalars(stmt).all())


def visible_attachments(db: Session, *, ticket: Ticket, actor: User) -> list[Attachment]:
    require_view(db, actor, ticket)
    stmt = select(Attachment).where(Attachment.ticket_id == ticket.id).order_by(Attachment.created_at.asc())
    return list(db.scalars(stmt).all())


def edit_comment(db: Session, *, comment: Comment, actor: User, body: str, source: str = "ui") -> Comment:
    _require_comment_moderation(actor)
    ticket = get_ticket(db, comment.ticket_id)
    require_view(db, actor, ticket)
    db.add(
        CommentRevision(
            id=new_id(),
            comment_id=comment.id,
            body=comment.body,
            action="edit",
            changed_by_user_id=actor.id,
        )
    )
    old = {"body": comment.body}
    comment.body = body
    comment.edited_at = datetime.now(timezone.utc)
    comment.changed_by_user_id = actor.id
    db.flush()
    audit(db, entity_type="Comment", entity_id=comment.id, action="comment.edit", actor=actor, source=source, old_value=old, new_value={"body": body})
    ticket_search.enqueue_ticket_index(ticket.id)
    return comment


def soft_delete_comment(db: Session, *, comment: Comment, actor: User, source: str = "ui") -> Comment:
    _require_comment_moderation(actor)
    ticket = get_ticket(db, comment.ticket_id)
    require_view(db, actor, ticket)
    if comment.deleted_at is not None:
        return comment
    db.add(
        CommentRevision(
            id=new_id(),
            comment_id=comment.id,
            body=comment.body,
            action="delete",
            changed_by_user_id=actor.id,
        )
    )
    old = {"deleted_at": None}
    comment.deleted_at = datetime.now(timezone.utc)
    comment.changed_by_user_id = actor.id
    db.flush()
    audit(db, entity_type="Comment", entity_id=comment.id, action="comment.soft_delete", actor=actor, source=source, old_value=old, new_value={"deleted_at": comment.deleted_at.isoformat()})
    ticket_search.enqueue_ticket_index(ticket.id)
    return comment


def comment_revisions(db: Session, *, comment: Comment, actor: User) -> list[CommentRevision]:
    if actor.kind != "internal":
        raise PermissionDenied("Comment history is internal only")
    ticket = get_ticket(db, comment.ticket_id)
    require_view(db, actor, ticket)
    return list(db.scalars(select(CommentRevision).where(CommentRevision.comment_id == comment.id).order_by(CommentRevision.changed_at.asc())).all())


def _require_comment_moderation(actor: User) -> None:
    if actor.kind != "internal" or actor.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Only Admin or Delivery Manager can edit or delete comments")


def _require_participant_management(ticket: Ticket, actor: User) -> None:
    if ticket.internal:
        raise ValidationError("Internal tickets do not have partner participants")
    if actor.kind == "partner":
        if ticket.owner_id != actor.id:
            raise PermissionDenied("Only the ticket owner can manage partner participants")
        return
    if actor.kind == "internal" and actor.internal_role in {"Admin", "DeliveryManager"}:
        return
    raise PermissionDenied("Admin or Delivery Manager role is required")


def _require_assign_permission(actor: User, ticket: Ticket, target_team: str) -> None:
    if actor.kind != "internal":
        raise PermissionDenied("Only internal users can assign tickets")
    if actor.internal_role in {"Admin", "DeliveryManager"}:
        return
    if actor.internal_role == "L1" and ticket.resolver_team == "L1" and target_team == "L2":
        return
    if actor.internal_role == "L2" and ticket.resolver_team == "L2" and target_team == "L3":
        return
    raise PermissionDenied("Resolver team assignment is not allowed for this role")


def _require_transition_permission(actor: User, ticket: Ticket, new_status: str) -> None:
    if actor.kind != "internal":
        raise PermissionDenied("Only internal users can transition ticket status in MVP")
    if actor.internal_role in {"Admin", "DeliveryManager"}:
        return
    if ticket.resolver_team == actor.internal_role and new_status in {"In progress", "Resolved", "Need more info", "Assigned", "Closed"}:
        return
    raise PermissionDenied("Status transition is not allowed for this role")


def _ensure_l3_issue(db: Session, ticket: Ticket, actor: User | None, source: str) -> None:
    try:
        gitlab.create_main_issue(db, ticket=ticket, actor=actor, source="system" if source == "ui" else source)
    except ValidationError:
        # Assignment must remain in place; the guard blocks In progress until the issue exists.
        pass


def _notify_delivery_managers(db: Session, ticket: Ticket, subject: str, body: str) -> None:
    managers = db.scalars(select(User).where(User.kind == "internal", User.internal_role == "DeliveryManager", User.active.is_(True))).all()
    for manager in managers:
        queue_email(db, event="new_ticket", recipient_email=manager.email, subject=subject, body=body, ticket_id=ticket.id)
