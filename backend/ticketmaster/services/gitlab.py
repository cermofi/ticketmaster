from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import GitLabLink, GitLabSyncEvent, Ticket, User
from ticketmaster.models.entities import new_id
from ticketmaster.services.audit import audit
from ticketmaster.services.errors import ConflictError, NotFoundError, ValidationError


def _status_from_gitlab(issue_state: str, board_list: str | None) -> str:
    if issue_state == "closed":
        return "Closed"
    if board_list in {"To Do", "In Progress", "Done"}:
        return board_list
    return "Open"


def check_configuration() -> dict:
    configured = bool(settings.gitlab_base_url and settings.gitlab_project_id and (settings.gitlab_token or settings.gitlab_dry_run))
    return {
        "configured": configured,
        "dry_run": settings.gitlab_dry_run,
        "base_url": settings.gitlab_base_url,
        "project_id": settings.gitlab_project_id,
    }


def create_main_issue(db: Session, *, ticket: Ticket, actor: User | None, source: str = "system") -> GitLabLink:
    existing = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id, GitLabLink.is_main.is_(True)))
    if existing:
        return existing
    if not settings.gitlab_project_id:
        _record_event(db, ticket.id, "create_issue", "failed", "GITLAB_PROJECT_ID is not configured")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.create_issue.error", actor=actor, source=source, new_value={"error": "GITLAB_PROJECT_ID is not configured"})
        raise ValidationError("GITLAB_PROJECT_ID is not configured")
    if settings.gitlab_dry_run:
        issue_iid = f"dry-{ticket.id[:8]}"
        link = GitLabLink(
            id=new_id(),
            ticket_id=ticket.id,
            project_id=settings.gitlab_project_id,
            issue_iid=issue_iid,
            issue_id=issue_iid,
            web_url=f"{settings.gitlab_base_url.rstrip('/')}/ticketmaster-dry-run/issues/{issue_iid}",
            status="Open",
            issue_state="opened",
        )
        db.add(link)
        _record_event(db, ticket.id, "create_issue", "ok", "Dry-run GitLab issue created")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.create_issue", actor=actor, source=source, new_value={"web_url": link.web_url, "dry_run": True})
        return link
    if not settings.gitlab_token:
        _record_event(db, ticket.id, "create_issue", "failed", "GITLAB_TOKEN is not configured")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.create_issue.error", actor=actor, source=source, new_value={"error": "GITLAB_TOKEN is not configured"})
        raise ValidationError("GITLAB_TOKEN is not configured")

    description = (
        f"Ticket ID: {ticket.id}\n"
        f"Ticket URL: {settings.base_url.rstrip()}/#/tickets/{ticket.id}\n"
        f"Ticket type: {ticket.type}\n"
        f"Priority: {ticket.priority}\n"
        f"Resolver team: {ticket.resolver_team}\n\n"
        f"{ticket.description}"
    )
    url = f"{settings.gitlab_base_url.rstrip('/')}/api/v4/projects/{quote_plus(settings.gitlab_project_id)}/issues"
    try:
        response = httpx.post(
            url,
            headers={"PRIVATE-TOKEN": settings.gitlab_token},
            json={"title": f"[TicketMaster] {ticket.title}", "description": description},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        _record_event(db, ticket.id, "create_issue", "failed", str(exc))
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.create_issue.error", actor=actor, source=source, new_value={"error": str(exc)})
        raise ValidationError(f"GitLab issue creation failed: {exc}") from exc
    link = GitLabLink(
        id=new_id(),
        ticket_id=ticket.id,
        project_id=str(payload.get("project_id") or settings.gitlab_project_id),
        issue_iid=str(payload["iid"]),
        issue_id=str(payload.get("id") or payload["iid"]),
        web_url=payload["web_url"],
        issue_state=payload.get("state", "opened"),
        status=_status_from_gitlab(payload.get("state", "opened"), None),
    )
    db.add(link)
    _record_event(db, ticket.id, "create_issue", "ok", link.web_url)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.create_issue", actor=actor, source=source, new_value={"web_url": link.web_url})
    return link


def sync_status(db: Session, *, ticket: Ticket, actor: User | None = None, source: str = "system") -> GitLabLink:
    link = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id, GitLabLink.is_main.is_(True)))
    if not link:
        raise NotFoundError("Ticket has no GitLab issue")
    if settings.gitlab_dry_run:
        link.last_synced_at = datetime.now(timezone.utc)
        _record_event(db, ticket.id, "sync_status", "ok", "Dry-run sync")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.sync_status", actor=actor, source=source, new_value={"status": link.status, "dry_run": True})
        return link
    if not settings.gitlab_token:
        raise ValidationError("GITLAB_TOKEN is not configured")
    url = f"{settings.gitlab_base_url.rstrip('/')}/api/v4/projects/{quote_plus(link.project_id)}/issues/{quote_plus(link.issue_iid)}"
    try:
        response = httpx.get(url, headers={"PRIVATE-TOKEN": settings.gitlab_token}, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        _record_event(db, ticket.id, "sync_status", "failed", str(exc))
        raise ValidationError(f"GitLab status sync failed: {exc}") from exc
    board_list = next((label for label in payload.get("labels", []) if label in {"To Do", "In Progress", "Done"}), None)
    link.issue_state = payload.get("state", link.issue_state)
    link.board_list = board_list
    link.status = _status_from_gitlab(link.issue_state, board_list)
    link.last_synced_at = datetime.now(timezone.utc)
    _record_event(db, ticket.id, "sync_status", "ok", link.status)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.sync_status", actor=actor, source=source, new_value={"status": link.status})
    return link


def _record_event(db: Session, ticket_id: str, action: str, status: str, message: str | None) -> GitLabSyncEvent:
    event = GitLabSyncEvent(id=new_id(), ticket_id=ticket_id, action=action, status=status, message=message)
    db.add(event)
    return event
