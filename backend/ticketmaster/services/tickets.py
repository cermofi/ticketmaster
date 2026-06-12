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
from ticketmaster.services.admin import resolve_client, resolve_partner, resolve_user
from ticketmaster.services.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError
from ticketmaster.services.notifications import queue_email


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
    if user.kind == "internal":
        if user.internal_role in {"Admin", "DeliveryManager"}:
            return True
        if user.internal_role in RESOLVER_TEAMS:
            return ticket.resolver_team == user.internal_role
        return False
    if ticket.internal:
        return False
    return ticket.partner_id == user.partner_id


def require_view(db: Session, user: User, ticket: Ticket) -> None:
    if not can_view_ticket(db, user, ticket):
        raise PermissionDenied("You are not allowed to view this ticket")


def can_comment(db: Session, user: User, ticket: Ticket) -> bool:
    if not user.active:
        raise PermissionDenied("Account is inactive")
    if ticket.status == "Closed":
        raise ValidationError("Closed tickets cannot be commented")
    if user.kind == "internal":
        return can_view_ticket(db, user, ticket)
    if not can_view_ticket(db, user, ticket):
        return False
    if ticket.system:
        return user.partner_role == "responsible"
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
    if not actor.active:
        raise PermissionDenied("Account is inactive")
    if actor.kind != "partner" or actor.partner_role != "responsible":
        raise PermissionDenied("Only responsible partner users can create partner tickets")
    validate_ticket_type(ticket_type)
    validate_priority(priority)
    actual_priority = "Critical" if ticket_type == "Security Issue" and priority == "Normal" else priority
    client = None
    if client_id:
        client = resolve_client(db, client_id)
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
        system=False,
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
    queue_email(db, event="ticket_created", recipient_email=actor.email, subject=f"Ticket created: {ticket.title}", body=f"Ticket {ticket.id} was created.", ticket_id=ticket.id)
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def create_partner_ticket_on_behalf(
    db: Session,
    *,
    actor: User,
    partner_id: str,
    owner_ref: str,
    ticket_type: str,
    priority: str,
    title: str,
    description: str,
    client_id: str | None = None,
    participant_ids: list[str] | None = None,
    source: str = "ui",
) -> Ticket:
    if not actor.active:
        raise PermissionDenied("Account is inactive")
    if actor.kind != "internal" or actor.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Only Admin or Delivery Manager can create partner tickets on behalf of a partner")
    validate_ticket_type(ticket_type)
    validate_priority(priority)
    partner = resolve_partner(db, partner_id)
    owner = resolve_user(db, owner_ref)
    if not owner.active or owner.kind != "partner" or owner.partner_role != "responsible" or owner.partner_id != partner.id:
        raise ValidationError("Ticket owner must be an active responsible user from the selected partner")
    actual_priority = "Critical" if ticket_type == "Security Issue" and priority == "Normal" else priority
    client = None
    if client_id:
        client = resolve_client(db, client_id)
        if client.partner_id != partner.id:
            raise ValidationError("Client must belong to the selected partner")
        assignment = db.scalar(select(ClientAssignment).where(ClientAssignment.client_id == client.id, ClientAssignment.user_id == owner.id))
        if not assignment:
            raise ValidationError("Ticket owner must be assigned as responsible person for the selected client")
    ticket = Ticket(
        id=new_id(),
        partner_id=partner.id,
        client_id=client.id if client else None,
        owner_id=owner.id,
        created_by_id=actor.id,
        internal=False,
        system=False,
        type=ticket_type,
        priority=actual_priority,
        status="New",
        title=title,
        description=description,
    )
    db.add(ticket)
    db.flush()
    _add_participant_if_missing(db, ticket.id, owner.id)
    for user_id in dict.fromkeys(participant_ids or []):
        user = db.get(User, user_id)
        if not user or user.kind != "partner" or user.partner_id != partner.id or not user.active:
            raise ValidationError("Participants must be active users from the selected partner")
        _add_participant_if_missing(db, ticket.id, user.id)
        if user.id != owner.id:
            queue_email(
                db,
                event="participant_added",
                recipient_email=user.email,
                subject=f"Added to ticket {ticket.title}",
                body=f"You were added to ticket {ticket.id}",
                ticket_id=ticket.id,
            )
    audit(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="ticket.create_partner_on_behalf",
        actor=actor,
        source=source,
        new_value={
            "status": ticket.status,
            "partner_id": partner.id,
            "owner_id": owner.id,
            "client_id": client.id if client else None,
            "created_by_id": actor.id,
            "created_on_behalf": True,
        },
    )
    _notify_delivery_managers(
        db,
        ticket,
        "New TicketMaster ticket created for partner",
        f"New partner ticket created on behalf of {partner.name}: {ticket.title}",
        exclude_user_id=actor.id,
    )
    queue_email(
        db,
        event="ticket_created_on_behalf",
        recipient_email=owner.email,
        subject=f"Ticket created: {ticket.title}",
        body=f"Ticket {ticket.id} was created for your partner by {actor.name}.",
        ticket_id=ticket.id,
    )
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
    if not actor.active:
        raise PermissionDenied("Account is inactive")
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
        system=False,
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


def create_system_ticket(
    db: Session,
    *,
    partner_id: str,
    ticket_type: str,
    priority: str,
    title: str,
    description: str,
    team: str | None = None,
    assignee_ref: str | None = None,
    actor: User | None = None,
    source: str = "api",
) -> Ticket:
    partner = resolve_partner(db, partner_id)
    validate_ticket_type(ticket_type)
    validate_priority(priority)
    if team and team not in RESOLVER_TEAMS:
        raise ValidationError("Invalid resolver team")
    assignee = None
    if assignee_ref:
        if not team:
            raise ValidationError("Assignee requires resolver team")
        assignee = resolve_user(db, assignee_ref)
        if not assignee.active or assignee.kind != "internal" or assignee.internal_role != team:
            raise ValidationError("Assignee must be an active internal user from the resolver team")
    ticket = Ticket(
        id=new_id(),
        partner_id=partner.id,
        client_id=None,
        owner_id=None,
        created_by_id=None,
        internal=False,
        system=True,
        type=ticket_type,
        priority=priority,
        status="Assigned" if team else "New",
        resolver_team=team,
        assignee_id=assignee.id if assignee else None,
        title=title,
        description=description,
    )
    db.add(ticket)
    db.flush()
    if assignee:
        _add_watcher_if_missing(db, ticket.id, assignee.id)
    if team == "L3":
        _ensure_l3_issue(db, ticket, actor, source)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.create_system", actor=actor, source=source, new_value={"partner_id": partner.id, "team": team, "status": ticket.status})
    _notify_delivery_managers(db, ticket, "New system TicketMaster ticket", f"New system ticket created: {ticket.title}")
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
        stmt = stmt.where(Ticket.resolver_team == actor.internal_role)
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
    if ticket.status == "Need more info":
        old = {"status": ticket.status}
        ticket.status = "Assigned" if ticket.resolver_team else "New"
        ticket.updated_at = datetime.now(timezone.utc)
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.status_auto_return", actor=actor, source=source, old_value=old, new_value={"status": ticket.status})
    if actor.kind == "partner":
        _notify_partner_comment_recipients(db, ticket, body)
    ticket_search.enqueue_ticket_index(ticket.id)
    return comment


def add_internal_note(db: Session, *, ticket: Ticket, actor: User, body: str, source: str = "ui") -> Comment:
    if not actor.active:
        raise PermissionDenied("Account is inactive")
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
    if ticket.resolver_team and ticket.resolver_team != team:
        raise ValidationError("Ticket resolver team cannot be changed")
    if actor:
        _require_assign_permission(actor, ticket, team)
    assignee = None
    if assignee_ref:
        assignee = resolve_user(db, assignee_ref)
        if not assignee.active or assignee.kind != "internal" or assignee.internal_role != team:
            raise ValidationError("Assignee must be an active internal user from the resolver team")
        _add_watcher_if_missing(db, ticket.id, assignee.id)
    old = {"status": ticket.status, "resolver_team": ticket.resolver_team, "assignee_id": ticket.assignee_id}
    ticket.status = "Assigned"
    ticket.resolver_team = team
    ticket.assignee_id = assignee.id if assignee else None
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()
    if team == "L3":
        try:
            _ensure_l3_issue(db, ticket, actor, source)
        except Exception:
            ticket.status = old["status"]
            ticket.resolver_team = old["resolver_team"]
            ticket.assignee_id = old["assignee_id"]
            ticket.updated_at = datetime.now(timezone.utc)
            db.flush()
            raise
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.assign", actor=actor, source=source, old_value=old, new_value={"status": ticket.status, "resolver_team": team, "assignee_id": ticket.assignee_id})
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def unassign_ticket(db: Session, *, ticket: Ticket, actor: User, source: str = "ui") -> Ticket:
    if actor.kind != "internal" or actor.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Only Admin or Delivery Manager can return tickets to the queue")
    if ticket.status == "Closed":
        raise ValidationError("Closed tickets cannot be unassigned")
    if not ticket.resolver_team:
        raise ValidationError("Ticket is not assigned to a resolver queue")
    if not ticket.assignee_id and ticket.status == "Assigned":
        return ticket
    old = {"status": ticket.status, "resolver_team": ticket.resolver_team, "assignee_id": ticket.assignee_id}
    ticket.status = "Assigned"
    ticket.assignee_id = None
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.unassign", actor=actor, source=source, old_value=old, new_value={"status": ticket.status, "resolver_team": ticket.resolver_team, "assignee_id": None})
    ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def transition_ticket(db: Session, *, ticket: Ticket, actor: User, new_status: str, source: str = "ui") -> Ticket:
    validate_transition(db, ticket=ticket, actor=actor, new_status=new_status)
    old = {"status": ticket.status}
    ticket.status = new_status
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.status_change", actor=actor, source=source, old_value=old, new_value={"status": new_status})
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
    if actor is None or actor.kind != "internal" or actor.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Only Admin or Delivery Manager can close tickets")
    if ticket.status != "Closed":
        old = {"status": ticket.status}
        ticket.status = "Closed"
        ticket.updated_at = datetime.now(timezone.utc)
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="ticket.close", actor=actor, source=source, old_value=old, new_value={"status": "Closed"})
        ticket_search.enqueue_ticket_index(ticket.id)
    return ticket


def transfer_owner(db: Session, *, ticket: Ticket, actor: User | None, new_owner_ref: str, source: str = "ui") -> Ticket:
    if ticket.internal or ticket.system:
        raise ValidationError("Only partner tickets have partner owners")
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
    raise PermissionDenied("Comment and internal note editing is disabled")


def soft_delete_comment(db: Session, *, comment: Comment, actor: User, source: str = "ui") -> Comment:
    raise PermissionDenied("Comment and internal note deletion is disabled")


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
    if ticket.system:
        if actor.kind == "partner" and actor.partner_id == ticket.partner_id and actor.partner_role == "responsible":
            return
        raise PermissionDenied("Only responsible partner users can manage system ticket participants")
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
    if ticket.resolver_team == actor.internal_role and target_team == actor.internal_role:
        return
    raise PermissionDenied("Resolver team assignment is not allowed for this role")


def _require_transition_permission(actor: User, ticket: Ticket, new_status: str) -> None:
    if actor.kind != "internal":
        raise PermissionDenied("Only internal users can transition ticket status in MVP")
    if actor.internal_role in {"Admin", "DeliveryManager"}:
        return
    if ticket.resolver_team == actor.internal_role and new_status in {"In progress", "Resolved", "Need more info", "Assigned"}:
        return
    raise PermissionDenied("Status transition is not allowed for this role")


def _ensure_l3_issue(db: Session, ticket: Ticket, actor: User | None, source: str) -> None:
    gitlab.create_main_issue(db, ticket=ticket, actor=actor, source="system" if source == "ui" else source)


def _notify_delivery_managers(db: Session, ticket: Ticket, subject: str, body: str, *, exclude_user_id: str | None = None) -> None:
    managers = db.scalars(select(User).where(User.kind == "internal", User.internal_role == "DeliveryManager", User.active.is_(True))).all()
    for manager in managers:
        if exclude_user_id and manager.id == exclude_user_id:
            continue
        queue_email(db, event="new_ticket", recipient_email=manager.email, subject=subject, body=body, ticket_id=ticket.id)


def _notify_partner_comment_recipients(db: Session, ticket: Ticket, body: str) -> None:
    subject = f"New partner comment: {ticket.title}"
    if ticket.assignee_id:
        assignee = db.get(User, ticket.assignee_id)
        if assignee and assignee.active:
            queue_email(db, event="partner_comment", recipient_email=assignee.email, subject=subject, body=body, ticket_id=ticket.id)
        return
    managers = db.scalars(select(User).where(User.kind == "internal", User.internal_role == "DeliveryManager", User.active.is_(True))).all()
    for manager in managers:
        queue_email(db, event="partner_comment", recipient_email=manager.email, subject=subject, body=body, ticket_id=ticket.id)
