from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import GitLabLink, GitLabSyncEvent, Ticket, User
from ticketmaster.models.constants import STATUSES, WORKFLOW_TRANSITIONS
from ticketmaster.models.entities import new_id
from ticketmaster.services.audit import audit
from ticketmaster.services.errors import NotFoundError, ValidationError
from ticketmaster.services import search as ticket_search

logger = logging.getLogger("ticketmaster.gitlab")

BOARD_LABELS = {"To Do", "In Progress", "Done"}


def _status_from_gitlab(issue_state: str, board_list: str | None) -> str:
    if issue_state == "closed":
        return "Closed"
    if board_list in BOARD_LABELS:
        return board_list
    return "Open"


def gitlab_status_to_ticket_status(gitlab_status: str) -> str | None:
    mapping = {
        "Open": "Queued",
        "To Do": "Queued",
        "In Progress": "In progress",
        "Done": "Resolved",
        "Closed": "Closed",
    }
    return mapping.get(gitlab_status)


def ticket_status_to_gitlab(ticket_status: str) -> tuple[str, str | None] | None:
    if ticket_status in {"Queued", "Assigned", "Need more info"}:
        return ("opened", "To Do")
    if ticket_status == "In progress":
        return ("opened", "In Progress")
    if ticket_status == "Resolved":
        return ("opened", "Done")
    if ticket_status == "Closed":
        return ("closed", None)
    return None


def _board_label_from_payload_labels(labels: list) -> str | None:
    titles: list[str] = []
    for label in labels:
        if isinstance(label, str):
            titles.append(label)
        elif isinstance(label, dict):
            title = label.get("title") or label.get("name")
            if title:
                titles.append(str(title))
    return next((label for label in titles if label in BOARD_LABELS), None)


def _validate_gitlab_ticket_transition(ticket: Ticket, new_status: str) -> str | None:
    if new_status not in STATUSES:
        return "Invalid ticket status"
    if new_status not in WORKFLOW_TRANSITIONS[ticket.status]:
        return f"Transition {ticket.status} -> {new_status} is not allowed"
    if new_status == "Assigned" and not ticket.assignee_id:
        return "Assigned status requires an assignee"
    if new_status == "In progress" and not ticket.assignee_id:
        return "In progress status requires an assignee"
    return None


def validate_webhook_token(token: str | None) -> bool:
    secret = settings.gitlab_webhook_secret
    if not secret:
        return False
    if not token:
        return False
    return hmac.compare_digest(token, secret)


def check_configuration() -> dict:
    configured = bool(settings.gitlab_base_url and settings.gitlab_project_id and (settings.gitlab_token or settings.gitlab_dry_run))
    return {
        "configured": configured,
        "dry_run": settings.gitlab_dry_run,
        "base_url": settings.gitlab_base_url,
        "project_id": settings.gitlab_project_id,
        "webhook_secret_configured": bool(settings.gitlab_webhook_secret),
    }


def find_main_link_by_issue(db: Session, *, project_id: str, issue_iid: str) -> GitLabLink | None:
    return db.scalar(
        select(GitLabLink).where(
            GitLabLink.project_id == str(project_id),
            GitLabLink.issue_iid == str(issue_iid),
            GitLabLink.is_main.is_(True),
        )
    )


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
    board_list = _board_label_from_payload_labels(payload.get("labels", []))
    link.issue_state = payload.get("state", link.issue_state)
    link.board_list = board_list
    link.status = _status_from_gitlab(link.issue_state, board_list)
    link.last_synced_at = datetime.now(timezone.utc)
    _record_event(db, ticket.id, "sync_status", "ok", link.status)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.sync_status", actor=actor, source=source, new_value={"status": link.status})
    return link


def apply_inbound_webhook(db: Session, *, payload: dict) -> dict:
    if payload.get("object_kind") != "issue":
        return {"handled": False, "reason": "ignored_event_type"}

    project = payload.get("project") or {}
    project_id = project.get("id") or payload.get("project_id")
    attrs = payload.get("object_attributes") or {}
    issue_iid = attrs.get("iid")
    if project_id is None or issue_iid is None:
        return {"handled": False, "reason": "missing_project_or_issue"}

    link = find_main_link_by_issue(db, project_id=str(project_id), issue_iid=str(issue_iid))
    if not link:
        return {"handled": False, "reason": "link_not_found"}

    ticket = db.get(Ticket, link.ticket_id)
    if not ticket:
        return {"handled": False, "reason": "ticket_not_found"}
    if ticket.resolver_team != "L3":
        return {"handled": False, "reason": "not_l3_ticket", "ticket_id": ticket.id}

    board_list = _board_label_from_payload_labels(attrs.get("labels") or [])
    issue_state = attrs.get("state", link.issue_state)
    gitlab_status = _status_from_gitlab(issue_state, board_list)
    link.issue_state = issue_state
    link.board_list = board_list
    link.status = gitlab_status
    link.last_synced_at = datetime.now(timezone.utc)

    target_status = gitlab_status_to_ticket_status(gitlab_status)
    if target_status is None:
        _record_event(db, ticket.id, "webhook_inbound", "skipped", f"Unmapped GitLab status: {gitlab_status}")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.webhook_inbound.skipped", actor=None, source="gitlab_webhook", new_value={"gitlab_status": gitlab_status})
        return {"handled": True, "ticket_id": ticket.id, "action": "skipped", "reason": "unmapped_status"}

    if ticket.status == target_status:
        _record_event(db, ticket.id, "webhook_inbound", "ok", f"Ticket already {target_status}")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.webhook_inbound.noop", actor=None, source="gitlab_webhook", new_value={"status": target_status, "gitlab_status": gitlab_status})
        return {"handled": True, "ticket_id": ticket.id, "action": "noop", "status": target_status}

    conflict = _validate_gitlab_ticket_transition(ticket, target_status)
    if conflict:
        message = f"Skipped GitLab status sync: {conflict}"
        _record_event(db, ticket.id, "webhook_inbound", "warning", message)
        audit(
            db,
            entity_type="Ticket",
            entity_id=ticket.id,
            action="gitlab.webhook_inbound.conflict",
            actor=None,
            source="gitlab_webhook",
            old_value={"status": ticket.status},
            new_value={"gitlab_status": gitlab_status, "target_status": target_status, "reason": conflict},
        )
        logger.warning("gitlab inbound conflict ticket_id=%s %s", ticket.id, conflict)
        return {"handled": True, "ticket_id": ticket.id, "action": "conflict", "reason": conflict}

    old = {"status": ticket.status}
    ticket.status = target_status
    ticket.updated_at = datetime.now(timezone.utc)
    _record_event(db, ticket.id, "webhook_inbound", "ok", f"{old['status']} -> {target_status}")
    audit(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="ticket.status_change",
        actor=None,
        source="gitlab_webhook",
        old_value=old,
        new_value={"status": target_status, "gitlab_status": gitlab_status},
    )
    ticket_search.enqueue_ticket_index(ticket.id)
    return {"handled": True, "ticket_id": ticket.id, "action": "updated", "status": target_status}


def push_ticket_status(db: Session, *, ticket: Ticket, actor: User | None = None, source: str = "system") -> None:
    if ticket.resolver_team != "L3":
        return
    link = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id, GitLabLink.is_main.is_(True)))
    if not link:
        return

    target = ticket_status_to_gitlab(ticket.status)
    if target is None:
        return
    issue_state, board_list = target

    if settings.gitlab_dry_run:
        link.issue_state = issue_state
        link.board_list = board_list
        link.status = _status_from_gitlab(issue_state, board_list)
        link.last_synced_at = datetime.now(timezone.utc)
        _record_event(db, ticket.id, "push_status", "ok", f"Dry-run push {ticket.status}")
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.push_status", actor=actor, source=source, new_value={"ticket_status": ticket.status, "gitlab_status": link.status, "dry_run": True})
        return

    if not settings.gitlab_token:
        message = "GITLAB_TOKEN is not configured"
        _record_event(db, ticket.id, "push_status", "failed", message)
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.push_status.error", actor=actor, source=source, new_value={"error": message, "ticket_status": ticket.status})
        logger.warning("gitlab outbound push failed ticket_id=%s %s", ticket.id, message)
        return

    try:
        _push_issue_status(link, issue_state=issue_state, board_list=board_list)
    except Exception as exc:
        _record_event(db, ticket.id, "push_status", "failed", str(exc))
        audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.push_status.error", actor=actor, source=source, new_value={"error": str(exc), "ticket_status": ticket.status})
        logger.warning("gitlab outbound push failed ticket_id=%s %s", ticket.id, exc)
        return

    link.issue_state = issue_state
    link.board_list = board_list
    link.status = _status_from_gitlab(issue_state, board_list)
    link.last_synced_at = datetime.now(timezone.utc)
    _record_event(db, ticket.id, "push_status", "ok", link.status)
    audit(db, entity_type="Ticket", entity_id=ticket.id, action="gitlab.push_status", actor=actor, source=source, new_value={"ticket_status": ticket.status, "gitlab_status": link.status})


def _push_issue_status(link: GitLabLink, *, issue_state: str, board_list: str | None) -> None:
    url = f"{settings.gitlab_base_url.rstrip('/')}/api/v4/projects/{quote_plus(link.project_id)}/issues/{quote_plus(link.issue_iid)}"
    headers = {"PRIVATE-TOKEN": settings.gitlab_token}
    current_labels: list[str] = []
    if board_list is not None:
        response = httpx.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        current_labels = _label_titles(response.json().get("labels", []))

    body: dict[str, str] = {}
    if issue_state == "closed":
        body["state_event"] = "close"
    elif link.issue_state == "closed" and issue_state == "opened":
        body["state_event"] = "reopen"
    if board_list is not None:
        preserved = [label for label in current_labels if label not in BOARD_LABELS]
        body["labels"] = ",".join([*preserved, board_list])

    if not body:
        return

    response = httpx.put(url, headers=headers, json=body, timeout=15)
    response.raise_for_status()


def _label_titles(labels: list) -> list[str]:
    titles: list[str] = []
    for label in labels:
        if isinstance(label, str):
            titles.append(label)
        elif isinstance(label, dict):
            title = label.get("title") or label.get("name")
            if title:
                titles.append(str(title))
    return titles


def _record_event(db: Session, ticket_id: str, action: str, status: str, message: str | None) -> GitLabSyncEvent:
    event = GitLabSyncEvent(id=new_id(), ticket_id=ticket_id, action=action, status=status, message=message)
    db.add(event)
    return event
