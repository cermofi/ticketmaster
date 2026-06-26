from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from ticketmaster.api.deps import CurrentUser, DbSession
from ticketmaster.core.config import settings
from ticketmaster.models import Attachment, AuditLog, Client, ClientAssignment, Comment, Partner, Ticket, User
from ticketmaster.models.constants import PRIORITIES, RESOLVER_TEAMS, STATUSES, TICKET_TYPES
from ticketmaster.models.entities import new_id
from ticketmaster.schemas.serializers import (
    attachment_to_dict,
    client_to_dict,
    comment_revision_to_dict,
    comment_to_dict,
    partner_to_dict,
    ticket_to_dict,
    tickets_to_dict,
    user_to_dict,
)
from ticketmaster.services import (
    account,
    admin,
    auth,
    gitlab,
    gitlab_delivery_tracking,
    malware,
    notifications,
    ticket_activity,
    ticket_exports,
    tickets,
)
from ticketmaster.services.audit import audit
from ticketmaster.services.audit_list import audit_filter_options, list_audit_logs, parse_audit_filter_datetime
from ticketmaster.services.audit_display import enrich_audit_rows
from ticketmaster.services.errors import NotFoundError, PermissionDenied, ValidationError
from ticketmaster.services.rate_limit import auth_rate_limit_key, check_rate_limit, clear_rate_limit
from ticketmaster.services.internal_roles import get_internal_roles, user_has_any_internal_role


router = APIRouter()


class LoginBody(BaseModel):
    email: str
    password: str


class DevSsoBody(BaseModel):
    email: str


class ActivateBody(BaseModel):
    token: str
    password: str


class SignInAsPartnerBody(BaseModel):
    user_id: str = Field(min_length=1)


class BackToAdminBody(BaseModel):
    return_token: str = Field(min_length=1)


class PartnerBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class InternalUserBody(BaseModel):
    email: str
    name: str
    role: str | None = None
    roles: list[str] | None = Field(default=None, min_length=1, max_length=3)


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


class ClientAssignmentBody(BaseModel):
    client_id: str
    user_id: str


class UserUpdateBody(BaseModel):
    email: str | None = Field(default=None, min_length=1, max_length=320)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=40)
    roles: list[str] | None = Field(default=None, min_length=1, max_length=3)
    active: bool | None = None


class AccountUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=1, max_length=320)


class ChangePasswordBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=300)
    new_password: str = Field(min_length=1, max_length=300)
    confirm_password: str = Field(min_length=1, max_length=300)


class TicketCreateBody(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    client_id: str | None = None
    participant_ids: list[str] = Field(default_factory=list)


class TicketOnBehalfCreateBody(BaseModel):
    partner_id: str
    owner_id: str
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


class SystemTicketCreateBody(BaseModel):
    type: str
    priority: str
    title: str
    description: str
    team: str | None = None
    assignee: str | None = None


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


class TicketTypeBody(BaseModel):
    type: str


class TicketPriorityBody(BaseModel):
    priority: str


class TransferOwnerBody(BaseModel):
    new_owner: str


class GitLabManualMappingBody(BaseModel):
    target_url: str = Field(min_length=1, max_length=1200)


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


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _ticket_detail(db: DbSession, user: User, ticket: Ticket) -> dict:
    data = ticket_to_dict(db, ticket, viewer=user, include_detail=True)
    data["available_transitions"] = tickets.available_transitions(db, ticket=ticket, actor=user)
    data["recent_activity"] = ticket_activity.ticket_activity(db, ticket=ticket, viewer=user, limit=3)
    return data


def _check_auth_rate_limit(request: Request, scope: str, identifier: str) -> None:
    check_rate_limit(auth_rate_limit_key(scope, _client_ip(request), identifier))


def _clear_auth_rate_limit(request: Request, scope: str, identifier: str) -> None:
    clear_rate_limit(auth_rate_limit_key(scope, _client_ip(request), identifier))


def _require_partner_api_access(user: User, partner_id: str, *, create: bool) -> None:
    if user.kind == "internal" and user_has_any_internal_role(user, {"Admin", "DeliveryManager"}):
        return
    if user.kind == "partner" and user.partner_id == partner_id:
        if create and user.partner_role != "responsible":
            raise PermissionDenied("Only responsible partner users can create system tickets through the partner API")
        return
    raise PermissionDenied("Partner API access is not allowed for this partner")


@router.get("/ready")
def ready(db: DbSession) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}


@router.post("/auth/login")
def login(db: DbSession, request: Request, body: LoginBody) -> dict:
    _check_auth_rate_limit(request, "login", body.email)
    try:
        user, token = auth.authenticate_email_password(db, body.email, body.password)
    except PermissionDenied:
        audit(db, entity_type="Auth", entity_id=body.email.lower(), action="auth.login_failed", source="ui", new_value=_request_audit_info(request, method="password", email=body.email.lower()))
        db.commit()
        raise
    _clear_auth_rate_limit(request, "login", body.email)
    audit(db, entity_type="Auth", entity_id=user.id, action="auth.login", actor=user, source="ui", new_value=_request_audit_info(request, method="password", email=user.email))
    db.commit()
    return {"token": token, "user": user_to_dict(user)}


@router.post("/auth/dev-sso")
def dev_sso(db: DbSession, request: Request, body: DevSsoBody) -> dict:
    if not settings.allow_dev_sso:
        raise PermissionDenied("Dev SSO is disabled in this environment")
    _check_auth_rate_limit(request, "login", body.email)
    try:
        user, token = auth.authenticate_dev_sso(db, body.email)
    except PermissionDenied:
        audit(db, entity_type="Auth", entity_id=body.email.lower(), action="auth.login_failed", source="ui", new_value=_request_audit_info(request, method="dev_sso", email=body.email.lower()))
        db.commit()
        raise
    _clear_auth_rate_limit(request, "login", body.email)
    audit(db, entity_type="Auth", entity_id=user.id, action="auth.login", actor=user, source="ui", new_value=_request_audit_info(request, method="dev_sso", email=user.email))
    db.commit()
    return {"token": token, "user": user_to_dict(user)}


@router.post("/auth/activate")
def activate(db: DbSession, request: Request, body: ActivateBody) -> dict:
    _check_auth_rate_limit(request, "activate", body.token)
    try:
        user, token = auth.activate_invitation(db, body.token, body.password)
    except (PermissionDenied, ValidationError):
        audit(
            db,
            entity_type="Auth",
            entity_id=body.token[:64],
            action="auth.activate_failed",
            source="ui",
            new_value=_request_audit_info(request, method="activation"),
        )
        db.commit()
        raise
    _clear_auth_rate_limit(request, "activate", body.token)
    audit(db, entity_type="Auth", entity_id=user.id, action="auth.activate", actor=user, source="ui", new_value=_request_audit_info(request, method="activation", email=user.email))
    db.commit()
    return {"token": token, "user": user_to_dict(user)}


@router.get("/auth/me")
def me(user: CurrentUser) -> dict:
    return user_to_dict(user)


@router.post("/auth/sign-in-as-partner")
def sign_in_as_partner(db: DbSession, user: CurrentUser, request: Request, body: SignInAsPartnerBody) -> dict:
    _check_auth_rate_limit(request, "sign-in-as-partner", user.id)
    partner_user, token, return_token = auth.sign_in_as_partner_user(db, actor=user, target_user_id=body.user_id)
    _clear_auth_rate_limit(request, "sign-in-as-partner", user.id)
    audit(
        db,
        entity_type="Auth",
        entity_id=partner_user.id,
        action="auth.sign_in_as_partner",
        actor=user,
        source="ui",
        new_value=_request_audit_info(
            request,
            method="sign_in_as_partner",
            partner_user_id=partner_user.id,
            partner_user_email=partner_user.email,
            partner_id=partner_user.partner_id,
        ),
    )
    db.commit()
    return {"token": token, "user": user_to_dict(partner_user), "return_token": return_token}


@router.post("/auth/back-to-admin")
def back_to_admin(db: DbSession, user: CurrentUser, request: Request, body: BackToAdminBody) -> dict:
    _check_auth_rate_limit(request, "back-to-admin", user.id)
    internal_user, token = auth.return_to_admin_user(db, actor=user, return_token=body.return_token)
    _clear_auth_rate_limit(request, "back-to-admin", user.id)
    audit(
        db,
        entity_type="Auth",
        entity_id=internal_user.id,
        action="auth.back_to_admin",
        actor=user,
        source="ui",
        new_value=_request_audit_info(
            request,
            method="back_to_admin",
            internal_user_id=internal_user.id,
            internal_user_email=internal_user.email,
            partner_user_id=user.id,
            partner_user_email=user.email,
        ),
    )
    db.commit()
    return {"token": token, "user": user_to_dict(internal_user)}


@router.get("/account/me")
def account_me(user: CurrentUser) -> dict:
    return account.profile_to_dict(user)


@router.patch("/account/me")
def account_update(db: DbSession, user: CurrentUser, body: AccountUpdateBody) -> dict:
    row = account.update_own_profile(db, user=user, name=body.name, email=body.email)
    db.commit()
    return account.profile_to_dict(row)


@router.post("/account/change-password")
def account_change_password(db: DbSession, user: CurrentUser, body: ChangePasswordBody) -> dict:
    account.change_own_password(
        db,
        user=user,
        current_password=body.current_password,
        new_password=body.new_password,
        confirm_password=body.confirm_password,
    )
    db.commit()
    return {"ok": True}


@router.get("/partners")
def partners_list(db: DbSession, user: CurrentUser) -> list[dict]:
    admin.require_internal(user)
    return [partner_to_dict(partner) for partner in db.scalars(select(Partner).order_by(Partner.name)).all()]


@router.post("/partners")
def partners_create(db: DbSession, user: CurrentUser, body: PartnerBody) -> dict:
    admin.require_admin_or_dm(user)
    partner = admin.create_partner(db, name=body.name, actor=user)
    db.commit()
    return partner_to_dict(partner)


@router.delete("/partners/{partner_id}")
def partners_delete(db: DbSession, user: CurrentUser, partner_id: str) -> dict:
    admin.require_admin(user)
    admin.delete_partner(db, partner_id=partner_id, actor=user)
    db.commit()
    return {"ok": True}


@router.get("/clients")
def clients_list(db: DbSession, user: CurrentUser, partner: str | None = None) -> list[dict]:
    if user.kind == "partner":
        stmt = select(Client).where(Client.partner_id == user.partner_id)
    else:
        admin.require_internal(user)
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
    client = admin.update_client(db, client_id=client_id, name=body.name, actor=user)
    db.commit()
    return client_to_dict(client)


@router.delete("/clients/{client_id}")
def clients_delete(db: DbSession, user: CurrentUser, client_id: str) -> dict:
    admin.require_admin_or_dm(user)
    admin.delete_client(db, client_id=client_id, actor=user)
    db.commit()
    return {"ok": True}


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
    payload: list[dict] = []
    for row in rows:
        payload.append(
            {
                "id": row.id,
                "client_id": row.client_id,
                "user_id": row.user_id,
                "user": user_to_dict(db.get(User, row.user_id)),
                "created_at": row.created_at,
            }
        )
    return payload


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
    elif user_has_any_internal_role(user, {"Admin", "DeliveryManager"}):
        stmt = select(User)
        if partner:
            resolved = admin.resolve_partner(db, partner)
            stmt = stmt.where(User.partner_id == resolved.id)
    else:
        admin.require_internal(user)
        stmt = select(User).where(User.kind == "partner", User.active.is_(True))
        if partner:
            resolved = admin.resolve_partner(db, partner)
            stmt = stmt.where(User.partner_id == resolved.id)
    return [user_to_dict(row) for row in db.scalars(stmt.order_by(User.email)).all()]


@router.post("/users/internal")
def users_create_internal(db: DbSession, user: CurrentUser, body: InternalUserBody) -> dict:
    admin.require_admin_or_dm(user)
    row = admin.create_internal_user(db, email=body.email, name=body.name, role=body.role, roles=body.roles, actor=user)
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
    row = admin.update_user(db, user_id=user_id, email=body.email, name=body.name, role=body.role, roles=body.roles, active=body.active, actor=user)
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
        select(Client).where(Client.partner_id == user.partner_id).order_by(Client.name)
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
        "items": tickets_to_dict(db, rows, viewer=user),
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


@router.post("/tickets/on-behalf")
def tickets_create_on_behalf(db: DbSession, user: CurrentUser, body: TicketOnBehalfCreateBody) -> dict:
    ticket = tickets.create_partner_ticket_on_behalf(
        db,
        actor=user,
        partner_id=body.partner_id,
        owner_ref=body.owner_id,
        ticket_type=body.type,
        priority=body.priority,
        title=body.title,
        description=body.description,
        client_id=body.client_id,
        participant_ids=body.participant_ids,
    )
    db.commit()
    return ticket_to_dict(db, ticket, viewer=user, include_detail=True)


@router.get("/tickets/export")
def tickets_export(
    db: DbSession,
    user: CurrentUser,
    format: str = "xlsx",
    search: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    type: str | None = None,
    resolver_team: str | None = None,
    partner_id: str | None = None,
    internal: bool | None = None,
) -> Response:
    result = ticket_exports.build_ticket_export(
        db,
        actor=user,
        export_format=format,
        filters={
            "search": search,
            "status": status,
            "priority": priority,
            "type": type,
            "resolver_team": resolver_team,
            "partner_id": partner_id,
            "internal": internal,
        },
    )
    audit(
        db,
        entity_type="TicketExport",
        entity_id=user.id,
        action="tickets.export",
        actor=user,
        source="ui",
        new_value={
            "format": format.lower().strip(),
            "ticket_count": result.ticket_count,
            "filters": result.filters,
            "viewer_kind": user.kind,
            "viewer_role": ", ".join(get_internal_roles(user)) if user.kind == "internal" else user.partner_role,
        },
    )
    db.commit()
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/partner-api/partners/{partner_id}/tickets")
def partner_api_tickets_list(
    db: DbSession,
    user: CurrentUser,
    partner_id: str,
    status: str | None = None,
    priority: str | None = None,
    type: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    partner = admin.resolve_partner(db, partner_id)
    _require_partner_api_access(user, partner.id, create=False)
    actual_limit = min(max(limit or settings.ticket_page_default_limit, 1), settings.ticket_page_max_limit)
    actual_offset = max(offset, 0)
    if user.kind == "partner":
        rows, total = tickets.list_visible_tickets_page(
            db,
            actor=user,
            status=status,
            priority=priority,
            ticket_type=type,
            partner_id=partner.id,
            internal=False,
            limit=actual_limit,
            offset=actual_offset,
        )
    else:
        stmt = select(Ticket).where(Ticket.internal.is_(False), Ticket.partner_id == partner.id)
        if status:
            stmt = stmt.where(Ticket.status == status)
        if priority:
            stmt = stmt.where(Ticket.priority == priority)
        if type:
            stmt = stmt.where(Ticket.type == type)
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = list(db.scalars(stmt.order_by(Ticket.created_at.desc()).limit(actual_limit).offset(actual_offset)).all())
    return {
        "items": tickets_to_dict(db, rows, viewer=user),
        "total": total,
        "limit": actual_limit,
        "offset": actual_offset,
    }


@router.post("/partner-api/partners/{partner_id}/tickets")
def partner_api_tickets_create(db: DbSession, user: CurrentUser, partner_id: str, body: SystemTicketCreateBody) -> dict:
    partner = admin.resolve_partner(db, partner_id)
    _require_partner_api_access(user, partner.id, create=True)
    ticket = tickets.create_system_ticket(
        db,
        partner_id=partner.id,
        ticket_type=body.type,
        priority=body.priority,
        title=body.title,
        description=body.description,
        team=body.team,
        assignee_ref=body.assignee,
        actor=user,
        source="api",
    )
    db.commit()
    return ticket_to_dict(db, ticket, viewer=user, include_detail=True)


@router.get("/tickets/{ticket_id}")
def tickets_detail(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.require_view(db, user, ticket)
    return _ticket_detail(db, user, ticket)


@router.get("/tickets/{ticket_id}/activity")
def tickets_activity(db: DbSession, user: CurrentUser, ticket_id: str) -> list[dict]:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.require_view(db, user, ticket)
    return ticket_activity.ticket_activity(db, ticket=ticket, viewer=user, limit=200)


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
    return _ticket_detail(db, user, ticket)


@router.post("/tickets/{ticket_id}/unassign")
def tickets_unassign(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.unassign_ticket(db, ticket=ticket, actor=user)
    db.commit()
    return _ticket_detail(db, user, ticket)


@router.post("/tickets/{ticket_id}/transition")
def tickets_transition(db: DbSession, user: CurrentUser, ticket_id: str, body: TransitionBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.transition_ticket(db, ticket=ticket, actor=user, new_status=body.status)
    db.commit()
    return _ticket_detail(db, user, ticket)


@router.post("/tickets/{ticket_id}/type")
def tickets_change_type(db: DbSession, user: CurrentUser, ticket_id: str, body: TicketTypeBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.change_ticket_type(db, ticket=ticket, actor=user, ticket_type=body.type)
    db.commit()
    return _ticket_detail(db, user, ticket)


@router.post("/tickets/{ticket_id}/priority")
def tickets_change_priority(db: DbSession, user: CurrentUser, ticket_id: str, body: TicketPriorityBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.change_ticket_priority(db, ticket=ticket, actor=user, priority=body.priority)
    db.commit()
    return _ticket_detail(db, user, ticket)


@router.post("/tickets/{ticket_id}/transfer-owner")
def tickets_transfer_owner(db: DbSession, user: CurrentUser, ticket_id: str, body: TransferOwnerBody) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.transfer_owner(db, ticket=ticket, actor=user, new_owner_ref=body.new_owner)
    db.commit()
    return _ticket_detail(db, user, ticket)


@router.post("/tickets/{ticket_id}/close")
def tickets_close(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.close_ticket(db, ticket=ticket, actor=user)
    db.commit()
    return _ticket_detail(db, user, ticket)


# TEMPORARY: admin-only ticket delete — remove this route when feature is retired.
@router.delete("/tickets/{ticket_id}")
def tickets_delete(db: DbSession, user: CurrentUser, ticket_id: str) -> dict:
    ticket = tickets.get_ticket(db, ticket_id)
    tickets.delete_ticket(db, ticket=ticket, actor=user)
    db.commit()
    return {"deleted": True, "id": ticket_id}


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


@router.get("/audit/options")
def audit_options(db: DbSession, user: CurrentUser) -> dict:
    if user.kind != "internal" or not user_has_any_internal_role(user, {"Admin", "DeliveryManager"}):
        raise PermissionDenied("Audit log is visible only for Admin and Delivery Manager")
    return audit_filter_options(db)


@router.get("/audit")
def audit_list(
    db: DbSession,
    user: CurrentUser,
    entity_id: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    action: str | None = None,
    source: str | None = None,
    entity_type: str | None = None,
    changed_by: str | None = None,
    search: str | None = None,
    has_details: bool | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    if user.kind != "internal" or not user_has_any_internal_role(user, {"Admin", "DeliveryManager"}):
        raise PermissionDenied("Audit log is visible only for Admin and Delivery Manager")
    changed_from = parse_audit_filter_datetime(from_) if from_ else None
    changed_to = parse_audit_filter_datetime(to) if to else None
    rows = list_audit_logs(
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
        limit=limit,
        offset=offset,
    )
    return enrich_audit_rows(db, rows)


@router.get("/gitlab/check")
def gitlab_check(user: CurrentUser) -> dict:
    if user.kind != "internal":
        raise PermissionDenied("GitLab check is internal only")
    return gitlab.check_configuration()


@router.get("/gitlab/delivery-tracking/meta")
def gitlab_delivery_tracking_meta(db: DbSession, user: CurrentUser) -> dict:
    admin.require_internal(user)
    return gitlab_delivery_tracking.list_dashboard_meta(db)


@router.get("/gitlab/delivery-tracking")
def gitlab_delivery_tracking_list(
    db: DbSession,
    user: CurrentUser,
    search: str | None = None,
    target_team: str | None = None,
    state: str | None = None,
    missing_mapping: bool | None = None,
    assignee: str | None = None,
    label: str | None = None,
    updated_since: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    admin.require_internal(user)
    actual_limit = min(max(limit or 100, 1), 500)
    actual_offset = max(offset, 0)
    changed_since = gitlab_delivery_tracking.parse_updated_since(updated_since)
    return gitlab_delivery_tracking.list_tracked_issues(
        db,
        search=search,
        target_team=target_team,
        state=state,
        missing_mapping=missing_mapping,
        assignee=assignee,
        label=label,
        updated_since=changed_since,
        sort_by=sort_by,
        sort_direction=sort_direction,
        limit=actual_limit,
        offset=actual_offset,
    )


@router.get("/gitlab/delivery-tracking/export")
def gitlab_delivery_tracking_export(
    db: DbSession,
    user: CurrentUser,
    format: str = "xlsx",
    search: str | None = None,
    target_team: str | None = None,
    state: str | None = None,
    missing_mapping: bool | None = None,
    assignee: str | None = None,
    label: str | None = None,
    updated_since: str | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
) -> Response:
    admin.require_internal(user)
    result = ticket_exports.build_delivery_tracking_export(
        db,
        actor=user,
        export_format=format,
        filters={
            "search": search,
            "target_team": target_team,
            "state": state,
            "missing_mapping": missing_mapping,
            "assignee": assignee,
            "label": label,
            "updated_since": updated_since,
        },
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    audit(
        db,
        entity_type="GitLabDeliveryTrackingExport",
        entity_id=user.id,
        action="gitlab.delivery_tracking.export",
        actor=user,
        source="ui",
        new_value={
            "format": format.lower().strip(),
            "rows": result.ticket_count,
            "filters": result.filters,
        },
    )
    db.commit()
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/gitlab/delivery-tracking/checks")
def gitlab_delivery_tracking_checks(
    db: DbSession,
    user: CurrentUser,
    issue_limit: int = 200,
) -> dict:
    admin.require_admin_or_dm(user)
    return gitlab_delivery_tracking.run_delivery_tracking_checks(db, issue_limit=issue_limit)


@router.post("/gitlab/delivery-tracking/sync")
def gitlab_delivery_tracking_sync(db: DbSession, user: CurrentUser) -> dict:
    admin.require_admin_or_dm(user)
    run = gitlab_delivery_tracking.sync_delivery_issues(db, triggered_by=f"manual:{user.id}")
    db.commit()
    return gitlab_delivery_tracking.serialize_sync_run(run)


@router.post("/gitlab/delivery-tracking/{tracked_issue_id}/manual-mapping")
def gitlab_delivery_tracking_set_manual_mapping(
    db: DbSession,
    user: CurrentUser,
    tracked_issue_id: str,
    body: GitLabManualMappingBody,
) -> dict:
    admin.require_admin_or_dm(user)
    tracked = gitlab_delivery_tracking.set_manual_mapping(
        db,
        tracked_issue_id=tracked_issue_id,
        target_url=body.target_url,
        actor=user,
    )
    db.commit()
    return gitlab_delivery_tracking.serialize_tracked_issue(tracked)


@router.post("/gitlab/webhook")
async def gitlab_webhook(request: Request, db: DbSession) -> dict:
    if not settings.gitlab_webhook_secret:
        raise HTTPException(status_code=503, detail="GitLab webhook is not configured")
    token = request.headers.get("X-Gitlab-Token")
    if not gitlab.validate_webhook_token(token):
        raise HTTPException(status_code=401, detail="Invalid GitLab webhook token")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    result = gitlab.apply_inbound_webhook(db, payload=payload)
    db.commit()
    return result


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
    if user.kind != "internal" or not user_has_any_internal_role(user, {"Admin", "DeliveryManager"}):
        raise PermissionDenied("Only Admin or Delivery Manager can test e-mail")
    row = notifications.queue_email(db, event="email_test", recipient_email=to, subject="TicketMaster test e-mail", body="TicketMaster SMTP test succeeded.", ticket_id=None)
    notifications.retry_failed(db)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/notifications/retry-failed")
def notifications_retry(db: DbSession, user: CurrentUser) -> dict:
    if user.kind != "internal" or not user_has_any_internal_role(user, {"Admin", "DeliveryManager"}):
        raise PermissionDenied("Only Admin or Delivery Manager can retry notifications")
    raise PermissionDenied("Manual notification retry is not available in MVP")
