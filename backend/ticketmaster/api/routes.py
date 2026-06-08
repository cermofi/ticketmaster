from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from ticketmaster.api.deps import CurrentUser, DbSession
from ticketmaster.core.config import settings
from ticketmaster.models import Attachment, AuditLog, Client, ClientAssignment, Comment, GitLabLink, Partner, Ticket, User
from ticketmaster.models.constants import PRIORITIES, RESOLVER_TEAMS, STATUSES, TICKET_TYPES
from ticketmaster.models.entities import new_id
from ticketmaster.schemas.serializers import (
    attachment_to_dict,
    audit_to_dict,
    client_to_dict,
    comment_revision_to_dict,
    comment_to_dict,
    partner_to_dict,
    ticket_to_dict,
    user_to_dict,
)
from ticketmaster.services import admin, auth, gitlab, malware, notifications, tickets
from ticketmaster.services.audit import audit
from ticketmaster.services.errors import NotFoundError, PermissionDenied, ValidationError
from ticketmaster.services.redis_client import get_redis


router = APIRouter()
_login_attempts: dict[str, list[float]] = {}


class LoginBody(BaseModel):
    email: str
    password: str


class DevSsoBody(BaseModel):
    email: str


class ActivateBody(BaseModel):
    token: str
    password: str


class PartnerBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class InternalUserBody(BaseModel):
    email: str
    name: str
    role: str


class PartnerUserBody(BaseModel):
    partner_id: str
    email: str
    name: str
    role: str


class ClientBody(BaseModel):
    partner_id: str
    name: str


class ClientUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    active: bool | None = None


class ClientAssignmentBody(BaseModel):
    client_id: str
    user_id: str


class UserUpdateBody(BaseModel):
    email: str | None = Field(default=None, min_length=1, max_length=320)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=40)
    active: bool | None = None


class PasswordResetBody(BaseModel):
    user_id: str | None = None


class TicketCreateBody(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    client_id: str | None = None
    participant_ids: list[str] = Field(default_factory=list)


class InternalTicketCreateBody(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    team: str | None = None


class CommentBody(BaseModel):
    body: str = Field(min_length=1)


class CommentEditBody(BaseModel):
    body: str = Field(min_length=1)


class ParticipantBody(BaseModel):
    user_id: str


class AssignBody(BaseModel):
    team: str
    assignee: str | None = None


class TransitionBody(BaseModel):
    status: str


class TransferOwnerBody(BaseModel):
    new_owner: str


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "ticketmaster-api"}


@router.get("/meta")
def meta() -> dict:
    return {
        "ticket_types": sorted(TICKET_TYPES),
        "priorities": sorted(PRIORITIES),
        "statuses": sorted(STATUSES),
        "resolver_teams": sorted(RESOLVER_TEAMS),
    }


def _request_audit_info(request: Request, **extra: str | None) -> dict:
    return {
        "ip": request.client.host if request.client else None,
        "x_forwarded_for": request.headers.get("x-forwarded-for"),
        "user_agent": request.headers.get("user-agent"),
        **extra,
    }


def _check_login_rate_limit(request: Request, email: str) -> None:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    key = f"{ip}:{email.lower()}"
    client = get_redis()
    if client:
        redis_key = f"ticketmaster:login-rate:{key}"
        attempts = client.incr(redis_key)
        if attempts == 1:
            client.expire(redis_key, settings.login_rate_limit_window_seconds)
        if attempts > settings.login_rate_limit_attempts:
            raise HTTPException(status_code=429, detail="Too many login attempts")
        return
    now = time.time()
    window_start = now - settings.login_rate_limit_window_seconds
    attempts = [stamp for stamp in _login_attempts.get(key, []) if stamp >= window_start]
    if len(attempts) >= settings.login_rate_limit_attempts:
        raise HTTPException(status_code=429, detail="Too many login attempts")
    attempts.append(now)
    _login_attempts[key] = attempts


def _clear_login_rate_limit(request: Request, email: str) -> None:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown")
    key = f"{ip}:{email.lower()}"
    client = get_redis()
    if client:
        client.delete(f"ticketmaster:login-rate:{key}")
    _login_attempts.pop(key, None)


@router.get("/ready")
def ready(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@router.post("/auth/login")
def login(db: DbSession, request: Request, body: LoginBody) -> dict:
    _check_login_rate_limit(request, body.email)
    try:
        user, token = auth.authenticate_email_password(db, body.email, body.password)
    except PermissionDenied:
        audit(db, entity_type="Auth", entity_id=body.email.lower(), action="auth.login_failed", source="ui", new_value=_request_audit_info(request, method="password", email=body.email.lower()))
        db.commit()
        raise
    _clear_login_rate_limit(request, body.email)
    audit(db, entity_type="Auth", entity_id=user.id, action="auth.login", actor=user, source="ui", new_value=_request_audit_info(request, method="password", email=user.email))
    db.commit()
    return {"token": token, "user": user_to_dict(user)}


@router.post("/auth/dev-sso")
def dev_sso(db: DbSession, request: Request, body: DevSsoBody) -> dict:
    _check_login_rate_limit(request, body.email)
    try:
        user, token = auth.authenticate_dev_sso(db, body.email)
    except PermissionDenied:
        audit(db, entity_type="Auth", entity_id=body.email.lower(), action="auth.login_failed", source="ui", new_value=_request_audit_info(request, method="dev_sso", email=body.email.lower()))
        db.commit()
        raise
    _clear_login_rate_limit(request, body.email)
    audit(db, entity_type="Auth", entity_id=user.id, action="auth.login", actor=user, source="ui", new_value=_request_audit_info(request, method="dev_sso", email=user.email))
    db.commit()
    return {"token": token, "user": user_to_dict(user)}


@router.post("/auth/activate")
def activate(db: DbSession, request: Request, body: ActivateBody) -> dict:
    user, token = auth.activate_invitation(db, body.token, body.password)
    audit(db, entity_type="Auth", entity_id=user.id, action="auth.activate", actor=user, source="ui", new_value=_request_audit_info(request, method="activation", email=user.email))
    db.commit()
    return {"token": token, "user": user_to_dict(user)}


@router.get("/auth/me")
def me(user: CurrentUser) -> dict:
    return user_to_dict(user)


@router.get("/partners")
def partners_list(db: DbSession, user: CurrentUser) -> list[dict]:
    admin.require_admin_or_dm(user)
    return [partner_to_dict(partner) for partner in db.scalars(select(Partner).order_by(Partner.name)).all()]


@router.post("/partners")
def partners_create(db: DbSession, user: CurrentUser, body: PartnerBody) -> dict:
    admin.require_admin(user)
    partner = admin.create_partner(db, name=body.name, actor=user)
    db.commit()
    return partner_to_dict(partner)


@router.delete("/partners/{partner_id}")
def partners_delete(db: DbSession, user: CurrentUser, partner_id: str) -> dict:
    admin.require_admin(user)
    partner = admin.deactivate_partner(db, partner_id=partner_id, actor=user)
    db.commit()
    return partner_to_dict(partner)


@router.get("/clients")
def clients_list(db: DbSession, user: CurrentUser, partner: str | None = None) -> list[dict]:
    if user.kind == "partner":
        stmt = select(Client).where(Client.partner_id == user.partner_id, Client.active.is_(True))
    else:
        admin.require_admin_or_dm(user)
        stmt = select(Client)
        if partner:
            resolved = admin.resolve_partner(db, partner)
            stmt = stmt.where(Client.partner_id == resolved.id)
    return [client_to_dict(client) for client in db.scalars(stmt.order_by(Client.name)).all()]


@router.post("/clients")
def clients_create(db: DbSession, user: CurrentUser, body: ClientBody) -> dict:
    admin.require_admin_or_dm(user)
    client = admin.create_client(db, partner_key_or_id=body.partner_id, name=body.name, actor=user)
    db.commit()
    return client_to_dict(client)


@router.patch("/clients/{client_id}")
def clients_update(db: DbSession, user: CurrentUser, client_id: str, body: ClientUpdateBody) -> dict:
    admin.require_admin_or_dm(user)
    client = admin.update_client(db, client_id=client_id, name=body.name, active=body.active, actor=user)
    db.commit()
    return client_to_dict(client)


@router.delete("/clients/{client_id}")
def clients_delete(db: DbSession, user: CurrentUser, client_id: str) -> dict:
    admin.require_admin_or_dm(user)
    client = admin.deactivate_client(db, client_id=client_id, actor=user)
    db.commit()
    return client_to_dict(client)


@router.post("/client-assignments")
def client_assign(db: DbSession, user: CurrentUser, body: ClientAssignmentBody) -> dict:
    admin.require_admin_or_dm(user)
    assignment = admin.assign_responsible_to_client(db, client_key_or_id=body.client_id, user_email_or_id=body.user_id, actor=user)
    db.commit()
    return {"id": assignment.id, "client_id": assignment.client_id, "user_id": assignment.user_id}


@router.get("/client-assignments")
def client_assignments_list(db: DbSession, user: CurrentUser, client_id: str) -> list[dict]:
    admin.require_admin_or_dm(user)
    rows = admin.list_client_assignments(db, client_id=client_id)
    return [
        {
            "id": row.id,
            "client_id": row.client_id,
            "user_id": row.user_id,
            "user": user_to_dict(db.get(User, row.user_id)),
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.delete("/client-assignments/{assignment_id}")
def client_assignments_delete(db: DbSession, user: CurrentUser, assignment_id: str) -> dict:
    admin.require_admin_or_dm(user)
    admin.remove_client_assignment(db, assignment_id=assignment_id, actor=user)
    db.commit()
    return {"ok": True}


@router.get("/users")
def users_list(db: DbSession, user: CurrentUser, partner: str | None = None) -> list[dict]:
    if user.kind == "partner":
        stmt = select(User).where(User.partner_id == user.partner_id, User.active.is_(True))
    else:
        admin.require_admin_or_dm(user)
        stmt = select(User)
        if partner:
            resolved = admin.resolve_partner(db, partner)
            stmt = stmt.where(User.partner_id == resolved.id)
    return [user_to_dict(row) for row in db.scalars(stmt.order_by(User.email)).all()]


@router.post("/users/internal")
def users_create_internal(db: DbSession, user: CurrentUser, body: InternalUserBody) -> dict:
    admin.require_admin(user)
    row = admin.create_internal_user(db, email=body.email, name=body.name, role=body.role, actor=user)
    db.commit()
    return user_to_dict(row)


@router.post("/users/partner")
def users_invite_partner(db: DbSession, user: CurrentUser, body: PartnerUserBody) -> dict:
    admin.require_admin_or_dm(user)
    row = admin.invite_partner_user(db, partner_key_or_id=body.partner_id, email=body.email, name=body.name, role=body.role, actor=user)
    db.commit()
    data = user_to_dict(row)
    data["invitation_token"] = row.invitation_token
    return data


@router.patch("/users/{user_id}")
def users_update(db: DbSession, user: CurrentUser, user_id: str, body: UserUpdateBody) -> dict:
    admin.require_admin_or_dm(user)
    row = admin.update_user(db, user_id=user_id, email=body.email, name=body.name, role=body.role, active=body.active, actor=user)
    db.commit()
    return user_to_dict(row)


@router.delete("/users/{user_id}")
def users_delete(db: DbSession, user: CurrentUser, user_id: str) -> dict:
    admin.require_admin_or_dm(user)
    row = admin.deactivate_user_by_id(db, user_id=user_id, actor=user)
    db.commit()
    return user_to_dict(row)


@router.post("/users/{user_id}/password-reset")
def users_password_reset(db: DbSession, user: CurrentUser, user_id: str) -> dict:
    admin.require_admin_or_dm(user)
    row = admin.send_password_reset(db, user_id=user_id, actor=user)
    db.commit()
    data = user_to_dict(row)
    data["reset_token"] = row.invitation_token
    return data


@router.post("/users/{email}/deactivate")
def users_deactivate(db: DbSession, user: CurrentUser, email: str) -> dict:
    admin.require_admin_or_dm(user)
    row = admin.deactivate_user(db, email=email, actor=user)
    db.commit()
    return user_to_dict(row)


@router.get("/partner-dashboard")
def partner_dashboard(db: DbSession, user: CurrentUser) -> dict:
    if user.kind != "partner" or not user.partner_id:
        raise PermissionDenied("Partner dashboard is available only to partner users")

    clients = db.scalars(
        select(Client)
        .where(Client.partner_id == user.partner_id, Client.active.is_(True))
        .order_by(Client.name)
    ).all()
    users = db.scalars(
        select(User)
        .where(User.partner_id == user.partner_id, User.kind == "partner", User.active.is_(True))
        .order_by(User.name)
    ).all()
    users_by_id = {row.id: row for row in users}
    client_ids = [client.id for client in clients]
    assignments = []
    if client_ids:
        assignments = db.scalars(
            select(ClientAssignment)
            .where(ClientAssignment.client_id.in_(client_ids))
            .order_by(ClientAssignment.created_at.asc())
        ).all()

    responsible_by_client: dict[str, list[dict]] = {client.id: [] for client in clients}
    for assignment in assignments:
        assigned_user = users_by_id.get(assignment.user_id)
        if assigned_user and assigned_user.partner_role == "responsible":
            responsible_by_client[assignment.client_id].append(user_to_dict(assigned_user))

    return {
        "clients": [
            {
                **client_to_dict(client),
                "responsible_users": responsible_by_client.get(client.id, []),
                "current_user_responsible": any(row["id"] == user.id for row in responsible_by_client.get(client.id, [])),
            }
            for client in clients
        ],
        "technical_users": [user_to_dict(row) for row in users if row.partner_role == "technical"],
    }


@router.get("/tickets")
def tickets_list(
    db: DbSession,
    user: CurrentUser,
    search: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    type: str | None = None,
    resolver_team: str | None = None,
    partner_id: str | None = None,
    internal: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    actual_limit = min(max(limit or settings.ticket_page_default_limit, 1), settings.ticket_page_max_limit)
    actual_offset = max(offset, 0)
    rows, total = tickets.list_visible_tickets_page(
        db,
        actor=user,
        search=search,
        status=status,
        priority=priority,
        ticket_type=type,
        resolver_team=resolver_team,
        partner_id=partner_id,
        internal=internal,
        limit=actual_limit,
        offset=actual_offset,
    )
    return {
        "items": [ticket_to_dict(db, ticket, viewer=user) for ticket in rows],
        "total": total,
        "limit": actual_limit,
        "offset": actual_offset,
    }


@router.post("/tickets")
def tickets_create(db: DbSession, user: CurrentUser, body: TicketCreateBody) -> dict:
    ticket = tickets.create_partner_ticket(
        db,
        actor=user,
        ticket_type=body.type,
        priority=body.priority,
        title=body.title,
        description=body.description,
        client_id=body.client_id,
        participant_ids=body.participant_ids,
    )
    db.commit()
    return ticket_to_dict(db, ticket, viewer=user, include_detail=True)


@router.post("/tickets/internal")
def tickets_create_internal(db: DbSession, user: CurrentUser, body: InternalTicketCreateBody) -> dict:
    ticket = tickets.create_internal_ticket(
        db,
        actor=user,
        ticket_type=body.type,
        priority=body.priority,
        title=body.title,
        description=body.description,
        team=body.team,
    )
    db.commit()
    return ticket_to_dict(db, ticket, viewer=user, include_detail=True)


@router.get("/tickets/{ticket_id}")
def tickets_detail(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.require_view(db, user, ticket)
    data = ticket_to_dict(db, ticket, viewer=user, include_detail=True)
    data["available_transitions"] = tickets.available_transitions(db, ticket=ticket, actor=user)
    return data


@router.post("/tickets/{ticket_id}/comments")
def tickets_comment(db: DbSession, user: CurrentUser, ticket_id: str, body: CommentBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    comment = tickets.add_comment(db, ticket=ticket, actor=user, body=body.body)
    db.commit()
    return comment_to_dict(comment, user)


@router.post("/tickets/{ticket_id}/internal-notes")
def tickets_internal_note(db: DbSession, user: CurrentUser, ticket_id: str, body: CommentBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    comment = tickets.add_internal_note(db, ticket=ticket, actor=user, body=body.body)
    db.commit()
    return comment_to_dict(comment, user)


@router.get("/tickets/{ticket_id}/comments")
def tickets_comments_list(db: DbSession, user: CurrentUser, ticket_id: str) -> list[dict]:
    ticket = tickets.get_ticket(db, ticket_id)
    rows = tickets.visible_comments(db, ticket=ticket, actor=user)
    return [comment_to_dict(row, db.get(User, row.author_id)) for row in rows]


@router.patch("/comments/{comment_id}")
def comments_edit(db: DbSession, user: CurrentUser, comment_id: str, body: CommentEditBody) -> dict:
    raise PermissionDenied("Comment and internal note editing is disabled")


@router.delete("/comments/{comment_id}")
def comments_delete(db: DbSession, user: CurrentUser, comment_id: str) -> dict:
    raise PermissionDenied("Comment and internal note deletion is disabled")


@router.get("/comments/{comment_id}/revisions")
def comments_revisions(db: DbSession, user: CurrentUser, comment_id: str) -> list[dict]:
    comment = db.get(Comment, comment_id)
    if not comment:
        raise NotFoundError("Comment not found")
    rows = tickets.comment_revisions(db, comment=comment, actor=user)
    return [comment_revision_to_dict(row) for row in rows]


@router.post("/tickets/{ticket_id}/participants")
def tickets_add_participant(db: DbSession, user: CurrentUser, ticket_id: str, body: ParticipantBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.add_participant(db, ticket=ticket, actor=user, user_id=body.user_id)
    db.commit()
    return ticket_to_dict(db, ticket, viewer=user, include_detail=True)


@router.delete("/tickets/{ticket_id}/participants/{user_id}")
def tickets_remove_participant(db: DbSession, user: CurrentUser, ticket_id: str, user_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.remove_participant(db, ticket=ticket, actor=user, user_id=user_id)
    db.commit()
    return ticket_to_dict(db, ticket, viewer=user, include_detail=True)


@router.post("/tickets/{ticket_id}/assign")
def tickets_assign(db: DbSession, user: CurrentUser, ticket_id: str, body: AssignBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.assign_ticket(db, ticket=ticket, actor=user, team=body.team, assignee_ref=body.assignee)
    db.commit()
    data = ticket_to_dict(db, ticket, viewer=user, include_detail=True)
    data["available_transitions"] = tickets.available_transitions(db, ticket=ticket, actor=user)
    return data


@router.post("/tickets/{ticket_id}/transition")
def tickets_transition(db: DbSession, user: CurrentUser, ticket_id: str, body: TransitionBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.transition_ticket(db, ticket=ticket, actor=user, new_status=body.status)
    db.commit()
    data = ticket_to_dict(db, ticket, viewer=user, include_detail=True)
    data["available_transitions"] = tickets.available_transitions(db, ticket=ticket, actor=user)
    return data


@router.post("/tickets/{ticket_id}/transfer-owner")
def tickets_transfer_owner(db: DbSession, user: CurrentUser, ticket_id: str, body: TransferOwnerBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.transfer_owner(db, ticket=ticket, actor=user, new_owner_ref=body.new_owner)
    db.commit()
    data = ticket_to_dict(db, ticket, viewer=user, include_detail=True)
    data["available_transitions"] = tickets.available_transitions(db, ticket=ticket, actor=user)
    return data


@router.post("/tickets/{ticket_id}/close")
def tickets_close(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.close_ticket(db, ticket=ticket, actor=user)
    db.commit()
    data = ticket_to_dict(db, ticket, viewer=user, include_detail=True)
    data["available_transitions"] = tickets.available_transitions(db, ticket=ticket, actor=user)
    return data


@router.get("/tickets/{ticket_id}/attachments")
def tickets_attachments_list(db: DbSession, user: CurrentUser, ticket_id: str) -> list[dict]:
    ticket = tickets.get_ticket(db, ticket_id)
    rows = tickets.visible_attachments(db, ticket=ticket, actor=user)
    return [attachment_to_dict(row, db.get(User, row.uploaded_by_id)) for row in rows]


@router.post("/tickets/{ticket_id}/attachments")
async def tickets_upload_attachment(
    db: DbSession,
    user: CurrentUser,
    ticket_id: str,
    file: UploadFile = File(...),
    comment_id: str | None = Form(default=None),
) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    if not tickets.can_comment(db, user, ticket):
        raise PermissionDenied("Only users who can comment can upload attachments")
    allowed_extensions = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".log", ".zip"}
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_extensions:
        raise ValidationError("Unsupported attachment type")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise ValidationError("Attachment exceeds 25 MB")
    malware.scan_upload(content, file.filename or f"attachment{suffix}")
    os.makedirs(settings.upload_dir, exist_ok=True)
    attachment_id = new_id()
    storage_path = str(Path(settings.upload_dir) / f"{attachment_id}{suffix}")
    Path(storage_path).write_bytes(content)
    attachment = Attachment(
        id=attachment_id,
        ticket_id=ticket.id,
        comment_id=comment_id,
        uploaded_by_id=user.id,
        filename=file.filename or f"attachment{suffix}",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        storage_path=storage_path,
    )
    db.add(attachment)
    audit(db, entity_type="Attachment", entity_id=attachment.id, action="attachment.upload", actor=user, new_value={"ticket_id": ticket.id, "filename": attachment.filename})
    db.commit()
    return {"id": attachment.id, "filename": attachment.filename, "size_bytes": attachment.size_bytes}


@router.get("/attachments/{attachment_id}/download")
def attachments_download(db: DbSession, user: CurrentUser, attachment_id: str) -> FileResponse:
    attachment = db.get(Attachment, attachment_id)
    if not attachment:
        raise NotFoundError("Attachment not found")
    ticket = tickets.get_ticket(db, attachment.ticket_id)
    tickets.require_view(db, user, ticket)
    path = Path(attachment.storage_path)
    if not path.exists():
        raise NotFoundError("Attachment file not found")
    return FileResponse(path, media_type=attachment.content_type, filename=attachment.filename)


@router.get("/audit")
def audit_list(db: DbSession, user: CurrentUser, entity_id: str | None = None) -> list[dict]:
    if user.kind != "internal" or user.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Audit log is visible only for Admin and Delivery Manager")
    stmt = select(AuditLog)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    stmt = stmt.order_by(AuditLog.changed_at.desc()).limit(200)
    return [audit_to_dict(row) for row in db.scalars(stmt).all()]


@router.get("/gitlab/check")
def gitlab_check(user: CurrentUser) -> dict:
    if user.kind != "internal":
        raise PermissionDenied("GitLab check is internal only")
    return gitlab.check_configuration()


@router.post("/tickets/{ticket_id}/gitlab/create-issue")
def gitlab_create_issue(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    if user.kind != "internal":
        raise PermissionDenied("GitLab issue creation is internal only")
    ticket = tickets.get_ticket(db, ticket_id)
    link = gitlab.create_main_issue(db, ticket=ticket, actor=user, source="ui")
    db.commit()
    return {"ticket_id": ticket.id, "web_url": link.web_url, "status": link.status}


@router.post("/tickets/{ticket_id}/gitlab/sync-status")
def gitlab_sync_status(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    if user.kind != "internal":
        raise PermissionDenied("GitLab sync is internal only")
    ticket = tickets.get_ticket(db, ticket_id)
    link = gitlab.sync_status(db, ticket=ticket, actor=user, source="ui")
    db.commit()
    return {"ticket_id": ticket.id, "status": link.status, "web_url": link.web_url}


@router.post("/email/test")
def email_test(db: DbSession, user: CurrentUser, to: str) -> dict:
    if user.kind != "internal" or user.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Only Admin or Delivery Manager can test e-mail")
    row = notifications.queue_email(db, event="email_test", recipient_email=to, subject="TicketMaster test e-mail", body="TicketMaster SMTP test succeeded.", ticket_id=None)
    notifications.retry_failed(db)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/notifications/retry-failed")
def notifications_retry(db: DbSession, user: CurrentUser) -> dict:
    if user.kind != "internal" or user.internal_role not in {"Admin", "DeliveryManager"}:
        raise PermissionDenied("Only Admin or Delivery Manager can retry notifications")
    sent = notifications.retry_failed(db)
    db.commit()
    return {"sent": sent}
