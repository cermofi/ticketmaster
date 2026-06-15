from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.core.slug import slugify
from ticketmaster.core.security import hash_password
from ticketmaster.models import Attachment, AuditLog, Client, ClientAssignment, Comment, CommentRevision, Partner, Ticket, TicketParticipant, TicketWatcher, User
from ticketmaster.models.constants import INTERNAL_ROLES, PARTNER_ROLES
from ticketmaster.models.entities import new_id
from ticketmaster.services.audit import audit
from ticketmaster.services.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError
from ticketmaster.services.notifications import queue_email


def require_admin_or_dm(actor: User | None) -> None:
    if actor is None or actor.kind != "internal" or actor.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Admin or Delivery Manager role is required")


def require_admin(actor: User | None) -> None:
    if actor is None or actor.kind != "internal" or actor.internal_role != "Admin":
        raise PermissionDenied("Admin role is required")


def _require_internal_user_management(actor: User | None, *, target: User | None = None, next_role: str | None = None) -> None:
    if target and target.kind == "internal" and target.internal_role == "Admin":
        require_admin(actor)
        return
    if next_role == "Admin":
        require_admin(actor)
        return
    require_admin_or_dm(actor)


def _clean_required(value: str, field: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{field} is required")
    return cleaned


def _clean_email(value: str) -> str:
    return _clean_required(value, "E-mail").lower()


def _active_admins_excluding(db: Session, user_id: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.kind == "internal", User.internal_role == "Admin", User.active.is_(True), User.id != user_id)
    )


def _guard_last_active_admin(db: Session, user: User, *, next_role: str | None = None, next_active: bool | None = None) -> None:
    if user.kind != "internal" or user.internal_role != "Admin" or not user.active:
        return
    removes_admin_role = next_role is not None and next_role != "Admin"
    deactivates_user = next_active is False
    if (removes_admin_role or deactivates_user) and _active_admins_excluding(db, user.id) == 0:
        raise ValidationError("Cannot remove the last active Admin user")


def resolve_partner(db: Session, key_or_id: str) -> Partner:
    partner = db.scalar(select(Partner).where((Partner.id == key_or_id) | (Partner.key == key_or_id)))
    if not partner:
        raise NotFoundError("Partner not found")
    return partner


def resolve_client(db: Session, key_or_id: str) -> Client:
    client = db.scalar(select(Client).where((Client.id == key_or_id) | (Client.key == key_or_id)))
    if not client:
        raise NotFoundError("Client not found")
    return client


def resolve_user(db: Session, email_or_id: str) -> User:
    user = db.scalar(select(User).where((User.id == email_or_id) | (User.email == email_or_id.lower())))
    if not user:
        raise NotFoundError("User not found")
    return user


def create_internal_user(
    db: Session,
    *,
    email: str,
    name: str,
    role: str,
    actor: User | None = None,
    source: str = "ui",
) -> User:
    if role not in INTERNAL_ROLES:
        raise ValidationError(f"Unsupported internal role: {role}")
    if actor is not None:
        _require_internal_user_management(actor, next_role=role)
    email = _clean_email(email)
    name = _clean_required(name, "Name")
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictError("User with this e-mail already exists")
    user = User(
        id=new_id(),
        email=email,
        name=name,
        kind="internal",
        internal_role=role,
        active=True,
    )
    db.add(user)
    db.flush()
    audit(db, entity_type="User", entity_id=user.id, action="user.create_internal", actor=actor, source=source, new_value={"email": user.email, "role": role})
    return user


def deactivate_user(db: Session, *, email: str, actor: User | None = None, source: str = "ui") -> User:
    user = resolve_user(db, email)
    return deactivate_user_by_id(db, user_id=user.id, actor=actor, source=source)


def deactivate_user_by_id(db: Session, *, user_id: str, actor: User | None = None, source: str = "ui") -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    if actor and actor.id == user.id:
        raise ValidationError("Cannot deactivate your own user")
    if user.kind == "internal":
        _require_internal_user_management(actor, target=user)
    _guard_last_active_admin(db, user, next_active=False)
    old = {"active": user.active}
    user.active = False
    user.invitation_token = None
    db.flush()
    audit(db, entity_type="User", entity_id=user.id, action="user.deactivate", actor=actor, source=source, old_value=old, new_value={"active": False})
    return user


def update_user(
    db: Session,
    *,
    user_id: str,
    email: str | None = None,
    name: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    actor: User | None = None,
    source: str = "ui",
) -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    if user.kind == "internal":
        _require_internal_user_management(actor, target=user, next_role=role)
    old = {
        "email": user.email,
        "name": user.name,
        "internal_role": user.internal_role,
        "partner_role": user.partner_role,
        "active": user.active,
    }
    if email is not None:
        cleaned_email = _clean_email(email)
        existing = db.scalar(select(User).where(User.email == cleaned_email, User.id != user.id))
        if existing:
            raise ConflictError("User with this e-mail already exists")
        user.email = cleaned_email
    if name is not None:
        user.name = _clean_required(name, "Name")
    if role is not None:
        role = _clean_required(role, "Role")
        if user.kind == "internal":
            if role not in INTERNAL_ROLES:
                raise ValidationError(f"Unsupported internal role: {role}")
            _guard_last_active_admin(db, user, next_role=role)
            user.internal_role = role
        else:
            if role not in PARTNER_ROLES:
                raise ValidationError(f"Unsupported partner role: {role}")
            user.partner_role = role
    if active is not None:
        if not active:
            if actor and actor.id == user.id:
                raise ValidationError("Cannot deactivate your own user")
            _guard_last_active_admin(db, user, next_active=False)
            user.invitation_token = None
        user.active = active
    new = {
        "email": user.email,
        "name": user.name,
        "internal_role": user.internal_role,
        "partner_role": user.partner_role,
        "active": user.active,
    }
    db.flush()
    if old != new:
        audit(db, entity_type="User", entity_id=user.id, action="user.update", actor=actor, source=source, old_value=old, new_value=new)
    return user


def create_partner(db: Session, *, name: str, actor: User | None = None, source: str = "ui") -> Partner:
    name = _clean_required(name, "Name")
    key_base = slugify(name)
    key = key_base
    suffix = 2
    while db.scalar(select(Partner).where(Partner.key == key)):
        key = f"{key_base}-{suffix}"
        suffix += 1
    partner = Partner(id=new_id(), key=key, name=name)
    db.add(partner)
    db.flush()
    audit(db, entity_type="Partner", entity_id=partner.id, action="partner.create", actor=actor, source=source, new_value={"key": key, "name": name})
    return partner


def delete_partner(db: Session, *, partner_id: str, actor: User | None = None, source: str = "ui") -> Partner:
    raise ValidationError("Partners cannot be deleted")


def create_client(db: Session, *, partner_key_or_id: str, name: str, actor: User | None = None, source: str = "ui") -> Client:
    partner = resolve_partner(db, partner_key_or_id)
    name = _clean_required(name, "Name")
    key_base = f"{partner.key}-{slugify(name)}"
    key = key_base
    suffix = 2
    while db.scalar(select(Client).where(Client.key == key)):
        key = f"{key_base}-{suffix}"
        suffix += 1
    client = Client(id=new_id(), key=key, partner_id=partner.id, name=name)
    db.add(client)
    db.flush()
    audit(db, entity_type="Client", entity_id=client.id, action="client.create", actor=actor, source=source, new_value={"partner_id": partner.id, "key": key, "name": name})
    return client


def update_client(
    db: Session,
    *,
    client_id: str,
    name: str | None = None,
    actor: User | None = None,
    source: str = "ui",
) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise NotFoundError("Client not found")
    old = {"name": client.name}
    if name is not None:
        client.name = _clean_required(name, "Name")
    new = {"name": client.name}
    db.flush()
    if old != new:
        audit(db, entity_type="Client", entity_id=client.id, action="client.update", actor=actor, source=source, old_value=old, new_value=new)
    return client


def delete_client(db: Session, *, client_id: str, actor: User | None = None, source: str = "ui") -> Client:
    raise ValidationError("Clients cannot be deleted")


def list_client_assignments(db: Session, *, client_id: str) -> list[ClientAssignment]:
    client = db.get(Client, client_id)
    if not client:
        raise NotFoundError("Client not found")
    return list(db.scalars(select(ClientAssignment).where(ClientAssignment.client_id == client.id).order_by(ClientAssignment.created_at.asc())).all())


def remove_client_assignment(db: Session, *, assignment_id: str, actor: User | None = None, source: str = "ui") -> None:
    assignment = db.get(ClientAssignment, assignment_id)
    if not assignment:
        raise NotFoundError("Responsible assignment not found")
    old = {"client_id": assignment.client_id, "user_id": assignment.user_id}
    db.delete(assignment)
    db.flush()
    audit(db, entity_type="Client", entity_id=old["client_id"], action="client.remove_responsible", actor=actor, source=source, old_value=old)


def invite_partner_user(
    db: Session,
    *,
    partner_key_or_id: str,
    email: str,
    name: str,
    role: str,
    actor: User | None = None,
    source: str = "ui",
) -> User:
    if role not in PARTNER_ROLES:
        raise ValidationError(f"Unsupported partner role: {role}")
    partner = resolve_partner(db, partner_key_or_id)
    email = _clean_email(email)
    name = _clean_required(name, "Name")
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictError("User with this e-mail already exists")
    token = secrets.token_urlsafe(32)
    user = User(
        id=new_id(),
        email=email,
        name=name,
        kind="partner",
        partner_id=partner.id,
        partner_role=role,
        invitation_token=token,
        password_hash=hash_password(settings.dev_password),
        active=True,
    )
    db.add(user)
    db.flush()
    audit(db, entity_type="User", entity_id=user.id, action="partner_user.invite", actor=actor, source=source, new_value={"email": user.email, "partner_id": partner.id, "role": role})
    queue_email(
        db,
        event="partner_user_invited",
        recipient_email=user.email,
        subject="TicketMaster invitation",
        body=f"You have been invited to TicketMaster. Activation token: {token}",
        ticket_id=None,
    )
    return user


def send_password_reset(db: Session, *, user_id: str, actor: User | None = None, source: str = "ui") -> User:
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    if user.kind == "internal":
        _require_internal_user_management(actor, target=user)
    if not user.active:
        raise ValidationError("Password reset can be sent only to active users")
    token = secrets.token_urlsafe(32)
    user.invitation_token = token
    db.flush()
    reset_url = f"{settings.base_url.rstrip('/')}/#/activate?token={token}"
    audit(db, entity_type="User", entity_id=user.id, action="user.password_reset", actor=actor, source=source, new_value={"email": user.email})
    queue_email(
        db,
        event="password_reset",
        recipient_email=user.email,
        subject="TicketMaster password reset",
        body=f"Use this link to set a new password: {reset_url}",
        ticket_id=None,
    )
    return user


def assign_responsible_to_client(
    db: Session,
    *,
    client_key_or_id: str,
    user_email_or_id: str,
    actor: User | None = None,
    source: str = "ui",
) -> ClientAssignment:
    client = resolve_client(db, client_key_or_id)
    user = resolve_user(db, user_email_or_id)
    if not user.active:
        raise ValidationError("Responsible user must be active")
    if user.kind != "partner" or user.partner_role != "responsible":
        raise ValidationError("Client responsible user must be a responsible partner user")
    if user.partner_id != client.partner_id:
        raise ValidationError("Client and responsible user must belong to the same partner")
    existing = db.scalar(select(ClientAssignment).where(ClientAssignment.client_id == client.id, ClientAssignment.user_id == user.id))
    if existing:
        return existing
    assignment = ClientAssignment(id=new_id(), client_id=client.id, user_id=user.id)
    db.add(assignment)
    db.flush()
    audit(db, entity_type="Client", entity_id=client.id, action="client.assign_responsible", actor=actor, source=source, new_value={"user_id": user.id})
    return assignment
