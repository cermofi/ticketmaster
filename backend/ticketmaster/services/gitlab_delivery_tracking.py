from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cmp_to_key
from itertools import islice
from urllib.parse import quote_plus, urlparse

import httpx
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import (
    GitLabDeliveryAlert,
    GitLabDeliveryAlertRead,
    GitLabIssueManualMapping,
    GitLabIssueSyncRun,
    GitLabTrackedIssue,
    User,
)
from ticketmaster.models.entities import new_id
from ticketmaster.services.errors import NotFoundError, ValidationError

logger = logging.getLogger("ticketmaster.gitlab.delivery_tracking")
SYNC_ADVISORY_LOCK_ID = 90503
CHECK_FINDINGS_LIMIT = 100
ALERT_CHANGES_PREVIEW_LIMIT = 4
DETAIL_NOTES_LIMIT = 80
CREATE_ISSUE_SUPPORTED_TYPES = {"issue", "incident", "test_case", "task"}
CREATE_ISSUE_DEFAULT_TYPES: tuple[dict[str, str], ...] = (
    {"value": "issue", "label": "Issue"},
    {"value": "incident", "label": "Incident"},
    {"value": "test_case", "label": "Test case"},
    {"value": "task", "label": "Task"},
)

ISSUE_URL_PATH_RE = re.compile(r"^/(?P<project_path>.+)/-/issues/(?P<issue_iid>\d+)/?$")
ISSUE_URL_IN_TEXT_RE = re.compile(r"https?://[^\s)]+/-/issues/\d+", re.IGNORECASE)
MOVED_NOTE_RE = re.compile(r"moved to\s+(?P<project_path>[A-Za-z0-9_.\-/]+)#(?P<issue_iid>\d+)", re.IGNORECASE)
SORT_FIELDS = {
    "delivery_issue",
    "ticket_id",
    "current_state",
    "target_team",
    "target_issue_url",
    "assignee",
    "labels",
    "sync_status",
    "last_gitlab_update",
    "delivery_url",
    "resolution_source",
}
SORT_DIRECTIONS = {"asc", "desc"}
ALERT_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("delivery_title", "delivery issue"),
    ("delivery_state", "delivery state"),
    ("delivery_labels", "delivery labels"),
    ("target_issue_iid", "team id"),
    ("target_state", "current state"),
    ("target_team_name", "target team"),
    ("target_url", "target issue url"),
    ("target_labels", "labels"),
    ("target_assignees", "assignee"),
    ("activity_comment_count", "comments"),
    ("activity_description_digest", "description"),
    ("sync_status", "sync status"),
    ("resolution_source", "resolution source"),
    ("target_missing", "target missing"),
    ("sync_error", "sync error"),
    ("last_gitlab_update", "last update"),
)


@dataclass
class IssueSyncOutcome:
    status: str
    used_manual_mapping: bool = False
    used_moved_to: bool = False
    used_note_fallback: bool = False


@dataclass
class TargetResolution:
    issue: dict | None
    source: str
    used_manual_mapping: bool
    used_moved_to: bool
    used_note_fallback: bool
    has_target_hint: bool
    fatal_error: str | None = None


class GitLabApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _map_gitlab_error(response: httpx.Response) -> GitLabApiError:
    status = response.status_code
    if status == 401:
        message = "GitLab API rejected token (401 unauthorized)"
    elif status == 403:
        message = "GitLab API access forbidden (403)"
    elif status == 404:
        message = "GitLab object not found (404)"
    elif status == 429:
        retry_after = response.headers.get("Retry-After")
        suffix = f", retry after {retry_after}s" if retry_after else ""
        message = f"GitLab API rate limited (429{suffix})"
    else:
        message = f"GitLab API request failed with status {status}"
    return GitLabApiError(message, status_code=status)


class GitLabReadOnlyClient:
    def __init__(self, *, base_url: str, token: str, timeout_seconds: float = 20) -> None:
        self._http = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/api/v4",
            headers={"PRIVATE-TOKEN": token},
            timeout=timeout_seconds,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, path: str, *, params: dict | None = None) -> httpx.Response:
        try:
            response = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise GitLabApiError("GitLab request failed") from exc
        if response.status_code >= 400:
            raise self._map_error(response)
        return response

    def _map_error(self, response: httpx.Response) -> GitLabApiError:
        return _map_gitlab_error(response)

    def list_project_issues(self, project_id: str, *, state: str = "all") -> list[dict]:
        issues: list[dict] = []
        page = 1
        while True:
            response = self._request(
                f"/projects/{quote_plus(str(project_id))}/issues",
                params={"state": state, "per_page": 100, "page": page},
            )
            payload = response.json()
            if not isinstance(payload, list):
                raise GitLabApiError("GitLab project issue list has invalid payload")
            issues.extend(payload)
            next_page = response.headers.get("X-Next-Page", "").strip()
            if not next_page:
                break
            page = int(next_page)
        return issues

    def get_project_issue(self, project_id: str, issue_iid: str) -> dict:
        response = self._request(f"/projects/{quote_plus(str(project_id))}/issues/{quote_plus(str(issue_iid))}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitLabApiError("GitLab issue payload is invalid")
        return payload

    def get_global_issue(self, issue_id: str) -> dict:
        response = self._request(f"/issues/{quote_plus(str(issue_id))}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitLabApiError("GitLab global issue payload is invalid")
        return payload

    def get_issue_notes(
        self,
        project_id: str,
        issue_iid: str,
        *,
        sort: str = "desc",
        order_by: str = "updated_at",
    ) -> list[dict]:
        notes: list[dict] = []
        page = 1
        while True:
            response = self._request(
                f"/projects/{quote_plus(str(project_id))}/issues/{quote_plus(str(issue_iid))}/notes",
                params={"per_page": 100, "page": page, "sort": sort, "order_by": order_by},
            )
            payload = response.json()
            if not isinstance(payload, list):
                raise GitLabApiError("GitLab notes payload is invalid")
            notes.extend(payload)
            next_page = response.headers.get("X-Next-Page", "").strip()
            if not next_page:
                break
            page = int(next_page)
        return notes

    def get_project(self, project_id_or_path: str) -> dict:
        response = self._request(f"/projects/{quote_plus(str(project_id_or_path))}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise GitLabApiError("GitLab project payload is invalid")
        return payload

    def list_project_labels(self, project_id_or_path: str) -> list[dict]:
        return self._list_paginated_dicts(
            f"/projects/{quote_plus(str(project_id_or_path))}/labels",
            params={"with_counts": "false", "include_ancestor_groups": "true"},
        )

    def list_project_milestones(self, project_id_or_path: str) -> list[dict]:
        return self._list_paginated_dicts(
            f"/projects/{quote_plus(str(project_id_or_path))}/milestones",
            params={"state": "active"},
        )

    def list_project_members(self, project_id_or_path: str) -> list[dict]:
        return self._list_paginated_dicts(
            f"/projects/{quote_plus(str(project_id_or_path))}/members/all",
            params={},
        )

    def list_accessible_projects(self, *, search: str | None = None) -> list[dict]:
        params = {
            "membership": "true",
            "archived": "false",
            "simple": "true",
            "order_by": "path",
            "sort": "asc",
            "min_access_level": "20",
        }
        search_text = _string_or_none(search)
        if search_text:
            params["search"] = search_text
        return self._list_paginated_dicts("/projects", params=params)

    def _list_paginated_dicts(self, path: str, *, params: dict[str, str] | None = None) -> list[dict]:
        rows: list[dict] = []
        page = 1
        while True:
            request_params = dict(params or {})
            request_params.update({"per_page": "100", "page": str(page)})
            response = self._request(path, params=request_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise GitLabApiError("GitLab list payload is invalid")
            rows.extend(item for item in payload if isinstance(item, dict))
            next_page = response.headers.get("X-Next-Page", "").strip()
            if not next_page:
                break
            page = int(next_page)
        return rows


def sync_enabled() -> bool:
    return _sync_configured() and settings.gitlab_sync_interval_seconds > 0


def _sync_configured() -> bool:
    return bool(
        settings.gitlab_base_url
        and settings.gitlab_token
        and settings.gitlab_delivery_project_id
    )


def list_target_teams() -> list[dict[str, str]]:
    return [{"project_id": project_id, "name": name} for project_id, name in settings.gitlab_target_projects]


def get_delivery_issue_create_meta(*, actor: User) -> dict:
    if actor.kind != "internal":
        raise ValidationError("Only internal users can create delivery issues")
    if not settings.gitlab_base_url:
        raise ValidationError("GITLAB_BASE_URL is not configured")
    if not settings.gitlab_delivery_project_id:
        raise ValidationError("GITLAB_DELIVERY_PROJECT_ID is not configured")
    if not settings.gitlab_token:
        raise ValidationError("GITLAB_TOKEN is not configured")

    client = GitLabReadOnlyClient(base_url=settings.gitlab_base_url, token=str(settings.gitlab_token))
    try:
        project = client.get_project(str(settings.gitlab_delivery_project_id))
        project_ref = _string_or_none(project.get("id")) or str(settings.gitlab_delivery_project_id)
        labels = [
            {
                "id": _int_or_none(label.get("id")),
                "title": _string_or_none(label.get("name")),
                "description": _string_or_none(label.get("description")),
                "color": _string_or_none(label.get("color")),
            }
            for label in client.list_project_labels(project_ref)
            if _string_or_none(label.get("name"))
        ]
        milestones = [
            {
                "id": _int_or_none(milestone.get("id")),
                "title": _string_or_none(milestone.get("title")),
                "description": _string_or_none(milestone.get("description")),
                "due_date": _string_or_none(milestone.get("due_date")),
                "web_url": _string_or_none(milestone.get("web_url")),
            }
            for milestone in client.list_project_milestones(project_ref)
            if _string_or_none(milestone.get("title"))
        ]
        assignees = [
            {
                "id": _int_or_none(member.get("id")),
                "username": _string_or_none(member.get("username")),
                "name": _string_or_none(member.get("name")),
                "avatar_url": _string_or_none(member.get("avatar_url")),
                "web_url": _string_or_none(member.get("web_url")),
                "state": _string_or_none(member.get("state")),
            }
            for member in client.list_project_members(project_ref)
            if _int_or_none(member.get("id")) is not None
        ]
    finally:
        client.close()

    current_assignee_id = _resolve_current_assignee_id(actor=actor, assignees=assignees)

    return {
        "project": {
            "id": _string_or_none(project.get("id")),
            "name": _string_or_none(project.get("name")),
            "path_with_namespace": _string_or_none(project.get("path_with_namespace")),
            "web_url": _string_or_none(project.get("web_url")),
        },
        "issue_types": list(CREATE_ISSUE_DEFAULT_TYPES),
        "labels": sorted(labels, key=lambda item: str(item["title"]).casefold()),
        "milestones": sorted(milestones, key=lambda item: str(item["title"]).casefold()),
        "assignees": sorted(
            assignees,
            key=lambda item: (str(item.get("name") or "").casefold(), str(item.get("username") or "").casefold()),
        ),
        "current_assignee_id": current_assignee_id,
    }


def list_move_issue_projects(*, actor: User, search: str | None = None) -> dict:
    _require_delivery_issue_write_access(actor=actor)

    client = GitLabReadOnlyClient(base_url=settings.gitlab_base_url, token=str(settings.gitlab_token))
    try:
        rows = client.list_accessible_projects(search=search)
    finally:
        client.close()

    projects: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for row in rows:
        project_id = _string_or_none(row.get("id"))
        if not project_id or project_id in seen_ids:
            continue
        seen_ids.add(project_id)
        projects.append(
            {
                "id": project_id,
                "name": _string_or_none(row.get("name")) or "",
                "path_with_namespace": _string_or_none(row.get("path_with_namespace")) or "",
                "web_url": _string_or_none(row.get("web_url")) or "",
            }
        )

    projects.sort(
        key=lambda item: (
            (item.get("path_with_namespace") or item.get("name") or "").casefold(),
            item.get("id") or "",
        )
    )
    return {"projects": projects}


def parse_updated_since(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if "T" not in raw:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError as exc:
        raise ValidationError("updated_since must be ISO date or datetime") from exc


def normalize_sort(sort_by: str | None, sort_direction: str | None) -> tuple[str, str]:
    normalized_sort_by = (sort_by or "last_gitlab_update").strip().lower().replace("-", "_")
    if normalized_sort_by not in SORT_FIELDS:
        normalized_sort_by = "last_gitlab_update"
    normalized_direction = (sort_direction or "desc").strip().lower()
    if normalized_direction not in SORT_DIRECTIONS:
        normalized_direction = "desc"
    return normalized_sort_by, normalized_direction


def list_dashboard_meta(db: Session) -> dict:
    configured_teams = list_target_teams()
    team_names = [name for _, name in settings.gitlab_target_projects]
    discovered_teams = db.scalars(
        select(GitLabTrackedIssue.target_team_name)
        .where(GitLabTrackedIssue.target_team_name.is_not(None))
        .distinct()
        .order_by(GitLabTrackedIssue.target_team_name.asc())
    ).all()
    for discovered in discovered_teams:
        if discovered and discovered not in team_names:
            configured_teams.append({"project_id": "", "name": discovered})
            team_names.append(discovered)
    states = [
        state
        for state in db.scalars(
            select(GitLabTrackedIssue.target_state)
            .where(GitLabTrackedIssue.target_state.is_not(None))
            .distinct()
            .order_by(GitLabTrackedIssue.target_state.asc())
        ).all()
        if state
    ]
    filter_rows = db.execute(
        select(
            GitLabTrackedIssue.target_assignees,
            GitLabTrackedIssue.target_labels,
            GitLabTrackedIssue.delivery_labels,
        )
    ).all()
    assignee_values: set[str] = set()
    label_values: set[str] = set()
    for target_assignees, target_labels, delivery_labels in filter_rows:
        for assignee in _normalize_assignees(target_assignees):
            name = _string_or_none(assignee.get("name")) or _string_or_none(assignee.get("username"))
            if name:
                assignee_values.add(name)
        effective_labels = _normalize_labels(target_labels)
        if not effective_labels:
            effective_labels = _normalize_labels(delivery_labels)
        for label in effective_labels:
            text = _string_or_none(label)
            if text:
                label_values.add(text)
    assignees = sorted(assignee_values, key=str.casefold)
    labels = sorted(label_values, key=str.casefold)
    latest_run = db.scalar(select(GitLabIssueSyncRun).order_by(GitLabIssueSyncRun.started_at.desc()))
    return {
        "configured": _sync_configured(),
        "target_teams": configured_teams,
        "states": states,
        "assignees": assignees,
        "labels": labels,
        "sync_interval_seconds": settings.gitlab_sync_interval_seconds,
        "last_sync_run": serialize_sync_run(latest_run) if latest_run else None,
    }


def create_delivery_issue(
    *,
    actor: User,
    title: str,
    description: str | None = None,
    labels: list[str] | None = None,
    assignee_ids: list[int] | None = None,
    milestone_id: int | None = None,
    due_date: str | None = None,
    confidential: bool = False,
    issue_type: str | None = None,
) -> dict:
    if actor.kind != "internal":
        raise ValidationError("Only internal users can create delivery issues")
    if not settings.gitlab_base_url:
        raise ValidationError("GITLAB_BASE_URL is not configured")
    if not settings.gitlab_delivery_project_id:
        raise ValidationError("GITLAB_DELIVERY_PROJECT_ID is not configured")
    if not settings.gitlab_token:
        raise ValidationError("GITLAB_TOKEN is not configured")

    normalized_title = (title or "").strip()
    if not normalized_title:
        raise ValidationError("Issue title is required")
    normalized_description = (description or "").strip()
    normalized_labels = _sanitize_issue_labels(labels)
    normalized_assignee_ids = sorted({value for value in (_int_or_none(item) for item in (assignee_ids or [])) if value})
    normalized_milestone_id = _int_or_none(milestone_id)
    normalized_due_date = _normalize_due_date(due_date)
    normalized_issue_type = _normalize_issue_type(issue_type)
    normalized_confidential = bool(confidential)

    request_body: dict[str, object] = {"title": normalized_title}
    if normalized_description:
        request_body["description"] = normalized_description
    if normalized_labels:
        request_body["labels"] = ",".join(normalized_labels)
    if normalized_assignee_ids:
        request_body["assignee_ids"] = normalized_assignee_ids
    if normalized_milestone_id is not None:
        request_body["milestone_id"] = normalized_milestone_id
    if normalized_due_date:
        request_body["due_date"] = normalized_due_date
    if normalized_confidential:
        request_body["confidential"] = True
    if normalized_issue_type:
        request_body["issue_type"] = normalized_issue_type

    url = (
        f"{settings.gitlab_base_url.rstrip('/')}/api/v4/projects/"
        f"{quote_plus(str(settings.gitlab_delivery_project_id))}/issues"
    )
    try:
        response = httpx.post(
            url,
            headers={"PRIVATE-TOKEN": str(settings.gitlab_token)},
            json=request_body,
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise ValidationError("GitLab issue creation failed: request error") from exc
    if response.status_code >= 400:
        raise ValidationError(f"GitLab issue creation failed: {_map_gitlab_error(response)}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise ValidationError("GitLab issue creation failed: invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise ValidationError("GitLab issue creation failed: invalid payload")

    return {
        "id": _string_or_none(payload.get("id")),
        "iid": _string_or_none(payload.get("iid")),
        "project_id": _string_or_none(payload.get("project_id")) or str(settings.gitlab_delivery_project_id),
        "title": _string_or_none(payload.get("title")) or normalized_title,
        "description": _string_or_none(payload.get("description")) or normalized_description,
        "state": _string_or_none(payload.get("state")) or "opened",
        "labels": _normalize_labels(payload.get("labels")),
        "web_url": _string_or_none(payload.get("web_url")),
        "created_at": _string_or_none(payload.get("created_at")),
        "assignee_ids": normalized_assignee_ids,
        "milestone_id": normalized_milestone_id,
        "due_date": normalized_due_date,
        "confidential": normalized_confidential,
        "issue_type": normalized_issue_type or "issue",
    }


def list_delivery_alerts(
    db: Session,
    *,
    actor: User,
    unread_only: bool = False,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    if actor.kind != "internal":
        raise ValidationError("Delivery tracking alerts are internal only")

    actual_limit = min(max(limit, 1), 200)
    actual_offset = max(offset, 0)
    read_alert_ids_stmt = select(GitLabDeliveryAlertRead.alert_id).where(GitLabDeliveryAlertRead.user_id == actor.id)

    total_stmt = select(func.count()).select_from(GitLabDeliveryAlert)
    if unread_only:
        total_stmt = total_stmt.where(~GitLabDeliveryAlert.id.in_(read_alert_ids_stmt))
    total = int(db.scalar(total_stmt) or 0)

    unread_count = int(
        db.scalar(
            select(func.count())
            .select_from(GitLabDeliveryAlert)
            .where(~GitLabDeliveryAlert.id.in_(read_alert_ids_stmt))
        )
        or 0
    )

    list_stmt = select(GitLabDeliveryAlert)
    if unread_only:
        list_stmt = list_stmt.where(~GitLabDeliveryAlert.id.in_(read_alert_ids_stmt))
    rows = db.scalars(
        list_stmt.order_by(GitLabDeliveryAlert.created_at.desc())
        .limit(actual_limit)
        .offset(actual_offset)
    ).all()

    row_ids = [row.id for row in rows]
    read_ids = _delivery_alert_read_ids(db, user_id=actor.id, alert_ids=row_ids)
    return {
        "items": [serialize_delivery_alert(row, is_read=row.id in read_ids) for row in rows],
        "total": total,
        "limit": actual_limit,
        "offset": actual_offset,
        "unread_count": unread_count,
    }


def mark_all_delivery_alerts_read(db: Session, *, actor: User) -> dict:
    if actor.kind != "internal":
        raise ValidationError("Delivery tracking alerts are internal only")

    alert_ids = db.scalars(select(GitLabDeliveryAlert.id)).all()
    if not alert_ids:
        return {"marked_count": 0, "unread_count": 0}

    existing = _delivery_alert_read_ids(db, user_id=actor.id, alert_ids=alert_ids)
    marked_count = 0
    now = _utcnow()
    for alert_id in alert_ids:
        if alert_id in existing:
            continue
        db.add(
            GitLabDeliveryAlertRead(
                id=new_id(),
                alert_id=alert_id,
                user_id=actor.id,
                read_at=now,
            )
        )
        marked_count += 1

    db.flush()
    unread_count = int(
        db.scalar(
            select(func.count())
            .select_from(GitLabDeliveryAlert)
            .where(
                ~GitLabDeliveryAlert.id.in_(
                    select(GitLabDeliveryAlertRead.alert_id).where(GitLabDeliveryAlertRead.user_id == actor.id)
                )
            )
        )
        or 0
    )
    return {"marked_count": marked_count, "unread_count": unread_count}


def serialize_delivery_alert(row: GitLabDeliveryAlert, *, is_read: bool) -> dict:
    raw_payload = row.changes if isinstance(row.changes, dict) else {}
    raw_changes = raw_payload.get("changes") if isinstance(raw_payload.get("changes"), list) else []
    changes: list[dict[str, str]] = []
    for item in raw_changes:
        if not isinstance(item, dict):
            continue
        changes.append(
            {
                "field": _string_or_none(item.get("field")) or "",
                "label": _string_or_none(item.get("label")) or "",
                "before": _string_or_none(item.get("before")) or "",
                "after": _string_or_none(item.get("after")) or "",
            }
        )

    return {
        "id": row.id,
        "tracked_issue_id": row.tracked_issue_id,
        "delivery_issue_iid": row.delivery_issue_iid,
        "delivery_title": row.delivery_title,
        "delivery_url": row.delivery_url,
        "target_url": row.target_url,
        "alert_kind": row.alert_kind,
        "message": row.message,
        "changes": changes,
        "change_summary": _delivery_alert_change_summary(changes),
        "created_at": row.created_at,
        "is_read": is_read,
    }


def _delivery_alert_read_ids(db: Session, *, user_id: str, alert_ids: list[str]) -> set[str]:
    if not alert_ids:
        return set()
    return set(
        db.scalars(
            select(GitLabDeliveryAlertRead.alert_id).where(
                GitLabDeliveryAlertRead.user_id == user_id,
                GitLabDeliveryAlertRead.alert_id.in_(alert_ids),
            )
        ).all()
    )


def _delivery_alert_change_summary(changes: list[dict[str, str]]) -> str:
    if not changes:
        return ""
    chunks: list[str] = []
    for change in islice(changes, ALERT_CHANGES_PREVIEW_LIMIT):
        label = _string_or_none(change.get("label")) or _string_or_none(change.get("field")) or "change"
        after = _string_or_none(change.get("after")) or "-"
        chunks.append(f"{label}: {after}")
    remaining = len(changes) - ALERT_CHANGES_PREVIEW_LIMIT
    if remaining > 0:
        chunks.append(f"+{remaining} more")
    return "; ".join(chunks)


def run_delivery_tracking_checks(db: Session, *, issue_limit: int = 200) -> dict:
    if not _sync_configured():
        raise ValidationError("GitLab delivery tracking is not configured")

    actual_limit = min(max(issue_limit, 1), 2000)
    delivery_project_id = str(settings.gitlab_delivery_project_id or "").strip()
    findings: list[dict] = []
    summary = {
        "missing_tracked_rows": 0,
        "orphaned_tracked_rows": 0,
        "invariant_failures": 0,
        "state_mismatches": 0,
        "resolution_mismatches": 0,
        "api_errors": 0,
    }

    tracked_rows = db.scalars(
        select(GitLabTrackedIssue).where(GitLabTrackedIssue.delivery_project_id == delivery_project_id)
    ).all()
    tracked_by_iid = {row.delivery_issue_iid: row for row in tracked_rows if row.delivery_issue_iid}
    mappings = db.scalars(
        select(GitLabIssueManualMapping).where(
            GitLabIssueManualMapping.delivery_project_id == delivery_project_id
        )
    ).all()
    mapping_by_iid = {row.delivery_issue_iid: row for row in mappings if row.delivery_issue_iid}

    client = GitLabReadOnlyClient(base_url=settings.gitlab_base_url, token=str(settings.gitlab_token))
    project_cache: dict[str, dict[str, str]] = {}
    try:
        try:
            issues = client.list_project_issues(delivery_project_id, state="all")
        except GitLabApiError as exc:
            summary["api_errors"] += 1
            return {
                "status": "error",
                "checked_at": _utcnow(),
                "delivery_project_id": delivery_project_id,
                "delivery_issues_total": 0,
                "checked_issues": 0,
                "issue_limit": actual_limit,
                "tracked_rows_total": len(tracked_rows),
                "summary": summary,
                "findings": [],
                "error_message": str(exc),
            }
        sorted_issues = sorted(
            issues,
            key=lambda payload: _safe_iid_sort(_string_or_none(payload.get("iid"))),
        )
        issue_iids = {
            _string_or_none(payload.get("iid")) or ""
            for payload in sorted_issues
        }

        for row in tracked_rows:
            if row.delivery_issue_iid not in issue_iids:
                summary["orphaned_tracked_rows"] += 1
                _append_check_finding(
                    findings,
                    issue_iid=row.delivery_issue_iid,
                    code="orphaned_tracked_row",
                    message="Tracked row exists but delivery issue was not returned by GitLab",
                )
            invariant_errors = _tracked_issue_invariant_errors(row)
            if invariant_errors:
                summary["invariant_failures"] += len(invariant_errors)
                for message in invariant_errors:
                    _append_check_finding(
                        findings,
                        issue_iid=row.delivery_issue_iid,
                        code="invariant_failure",
                        message=message,
                    )

        checked_issues = 0
        for payload in sorted_issues[:actual_limit]:
            checked_issues += 1
            delivery_issue_iid = _string_or_none(payload.get("iid")) or ""
            tracked = tracked_by_iid.get(delivery_issue_iid)
            if tracked is None:
                summary["missing_tracked_rows"] += 1
                _append_check_finding(
                    findings,
                    issue_iid=delivery_issue_iid,
                    code="missing_tracked_row",
                    message="Delivery issue exists in GitLab but not in tracked table",
                )
                continue

            expected_delivery_state = _string_or_none(payload.get("state")) or ""
            if (tracked.delivery_state or "") != expected_delivery_state:
                summary["state_mismatches"] += 1
                _append_check_finding(
                    findings,
                    issue_iid=delivery_issue_iid,
                    code="delivery_state_mismatch",
                    message="Stored delivery state differs from GitLab delivery issue state",
                    expected=expected_delivery_state,
                    actual=tracked.delivery_state,
                )

            try:
                resolution = _resolve_target_issue(
                    client=client,
                    delivery_payload=payload,
                    mapping=mapping_by_iid.get(delivery_issue_iid),
                    project_cache=project_cache,
                )
            except GitLabApiError as exc:
                summary["api_errors"] += 1
                _append_check_finding(
                    findings,
                    issue_iid=delivery_issue_iid,
                    code="resolution_api_error",
                    message=f"GitLab API error during resolution check: {exc}",
                )
                continue

            expected_sync_status = _expected_sync_status(resolution)
            if tracked.sync_status != expected_sync_status:
                summary["resolution_mismatches"] += 1
                _append_check_finding(
                    findings,
                    issue_iid=delivery_issue_iid,
                    code="sync_status_mismatch",
                    message="Stored sync_status differs from resolver expectation",
                    expected=expected_sync_status,
                    actual=tracked.sync_status,
                )

            if expected_sync_status == "ok" and resolution.issue is not None:
                expected_project_id = _string_or_none(resolution.issue.get("project_id"))
                expected_issue_iid = _string_or_none(resolution.issue.get("iid"))
                if tracked.target_project_id != expected_project_id:
                    summary["resolution_mismatches"] += 1
                    _append_check_finding(
                        findings,
                        issue_iid=delivery_issue_iid,
                        code="target_project_mismatch",
                        message="Stored target project differs from resolver expectation",
                        expected=expected_project_id,
                        actual=tracked.target_project_id,
                    )
                if tracked.target_issue_iid != expected_issue_iid:
                    summary["resolution_mismatches"] += 1
                    _append_check_finding(
                        findings,
                        issue_iid=delivery_issue_iid,
                        code="target_issue_mismatch",
                        message="Stored target issue IID differs from resolver expectation",
                        expected=expected_issue_iid,
                        actual=tracked.target_issue_iid,
                    )
            elif expected_sync_status == "in_delivery":
                if tracked.target_project_id or tracked.target_issue_iid or tracked.target_url:
                    summary["resolution_mismatches"] += 1
                    _append_check_finding(
                        findings,
                        issue_iid=delivery_issue_iid,
                        code="in_delivery_has_target_fields",
                        message="Issue marked in_delivery should not store target issue fields",
                    )
            elif expected_sync_status == "target_missing":
                if not tracked.target_missing:
                    summary["resolution_mismatches"] += 1
                    _append_check_finding(
                        findings,
                        issue_iid=delivery_issue_iid,
                        code="target_missing_flag_mismatch",
                        message="Issue expected as target_missing but target_missing flag is false",
                    )

        status = "ok" if not findings else "warning"
        return {
            "status": status,
            "checked_at": _utcnow(),
            "delivery_project_id": delivery_project_id,
            "delivery_issues_total": len(sorted_issues),
            "checked_issues": checked_issues,
            "issue_limit": actual_limit,
            "tracked_rows_total": len(tracked_rows),
            "summary": summary,
            "findings": findings,
        }
    finally:
        client.close()


def list_tracked_issues(
    db: Session,
    *,
    search: str | None = None,
    target_team: str | None = None,
    state: str | None = None,
    missing_mapping: bool | None = None,
    assignee: str | None = None,
    label: str | None = None,
    updated_since: datetime | None = None,
    sort_by: str | None = None,
    sort_direction: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    stmt = select(GitLabTrackedIssue)
    if target_team:
        stmt = stmt.where(GitLabTrackedIssue.target_team_name == target_team)
    if state:
        stmt = stmt.where(
            or_(
                GitLabTrackedIssue.target_state == state,
                and_(
                    GitLabTrackedIssue.sync_status == "in_delivery",
                    GitLabTrackedIssue.delivery_state == state,
                ),
            )
        )
    if missing_mapping is True:
        stmt = stmt.where(GitLabTrackedIssue.target_missing.is_(True))
    elif missing_mapping is False:
        stmt = stmt.where(GitLabTrackedIssue.target_missing.is_(False))
    if updated_since:
        stmt = stmt.where(
            or_(
                GitLabTrackedIssue.target_updated_at >= updated_since,
                GitLabTrackedIssue.delivery_updated_at >= updated_since,
            )
        )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                GitLabTrackedIssue.delivery_title.ilike(pattern),
                GitLabTrackedIssue.delivery_issue_iid.ilike(pattern),
                GitLabTrackedIssue.target_issue_iid.ilike(pattern),
            )
        )

    all_rows = _dedupe_tracked_issue_rows(db.scalars(stmt).all())
    if assignee:
        all_rows = [row for row in all_rows if _row_matches_assignee_filter(row, assignee)]
    if label:
        all_rows = [row for row in all_rows if _row_matches_label_filter(row, label)]
    total = len(all_rows)
    normalized_sort_by, normalized_sort_direction = normalize_sort(sort_by, sort_direction)
    sorted_rows = _sort_tracked_issue_rows(all_rows, sort_by=normalized_sort_by, sort_direction=normalized_sort_direction)
    paged_rows = sorted_rows[max(offset, 0): max(offset, 0) + max(limit, 0)]
    return {
        "items": [serialize_tracked_issue(row) for row in paged_rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort_by": normalized_sort_by,
        "sort_direction": normalized_sort_direction,
    }


def get_tracked_issue_detail(db: Session, *, actor: User, tracked_issue_id: str) -> dict:
    if actor.kind != "internal":
        raise ValidationError("Delivery tracking details are internal only")
    tracked = db.get(GitLabTrackedIssue, tracked_issue_id)
    if tracked is None:
        raise NotFoundError("Tracked issue not found")
    if not settings.gitlab_base_url:
        raise ValidationError("GITLAB_BASE_URL is not configured")
    if not settings.gitlab_token:
        raise ValidationError("GITLAB_TOKEN is not configured")

    project_id = tracked.target_project_id or tracked.delivery_project_id
    issue_iid = tracked.target_issue_iid or tracked.delivery_issue_iid
    source_issue = "target" if tracked.target_project_id and tracked.target_issue_iid else "delivery"
    client = GitLabReadOnlyClient(base_url=settings.gitlab_base_url, token=str(settings.gitlab_token))
    assignable_users_payload: list[dict] = []
    try:
        issue_payload = client.get_project_issue(project_id, issue_iid)
        notes_payload = client.get_issue_notes(project_id, issue_iid, sort="asc", order_by="created_at")
        detail_project_id = _string_or_none(issue_payload.get("project_id")) or project_id
        try:
            assignable_users_payload = client.list_project_members(detail_project_id)
        except GitLabApiError as exc:
            logger.info("gitlab detail members unavailable: project_id=%s error=%s", detail_project_id, exc)
    except GitLabApiError as exc:
        raise ValidationError(f"GitLab issue detail unavailable: {exc}") from exc
    finally:
        client.close()

    notes = [_normalize_issue_note(note) for note in notes_payload if isinstance(note, dict)]
    if len(notes) > DETAIL_NOTES_LIMIT:
        notes = notes[-DETAIL_NOTES_LIMIT:]

    return {
        "tracked_issue": serialize_tracked_issue(tracked),
        "source_issue": source_issue,
        "issue": _normalize_issue_detail(issue_payload),
        "notes": notes,
        "assignable_users": _normalize_project_members(assignable_users_payload),
    }


def close_tracked_issue(db: Session, *, actor: User, tracked_issue_id: str) -> dict:
    _require_delivery_issue_write_access(actor=actor)
    _, project_id, issue_iid = _resolve_tracked_issue_reference(db, tracked_issue_id=tracked_issue_id)
    payload = _request_gitlab_issue_mutation(
        method="PUT",
        project_id=project_id,
        issue_iid=issue_iid,
        body={"state_event": "close"},
        action_label="GitLab close issue failed",
    )
    return _normalize_issue_detail(payload)


def edit_tracked_issue(
    db: Session,
    *,
    actor: User,
    tracked_issue_id: str,
    title: str,
    description: str | None = None,
) -> dict:
    _require_delivery_issue_write_access(actor=actor)
    _, project_id, issue_iid = _resolve_tracked_issue_reference(db, tracked_issue_id=tracked_issue_id)
    normalized_title = _string_or_none(title)
    if not normalized_title:
        raise ValidationError("Issue title is required")
    normalized_description = "" if description is None else str(description)
    payload = _request_gitlab_issue_mutation(
        method="PUT",
        project_id=project_id,
        issue_iid=issue_iid,
        body={"title": normalized_title, "description": normalized_description},
        action_label="GitLab issue edit failed",
    )
    return _normalize_issue_detail(payload)


def move_tracked_issue(
    db: Session,
    *,
    actor: User,
    tracked_issue_id: str,
    to_project_id: str,
) -> dict:
    _require_delivery_issue_write_access(actor=actor)
    _, project_id, issue_iid = _resolve_tracked_issue_reference(db, tracked_issue_id=tracked_issue_id)
    normalized_target_project = _string_or_none(to_project_id)
    if not normalized_target_project:
        raise ValidationError("to_project_id is required")
    payload = _request_gitlab_issue_mutation(
        method="POST",
        project_id=project_id,
        issue_iid=issue_iid,
        body={"to_project_id": normalized_target_project},
        action_label="GitLab issue move failed",
        endpoint_suffix="/move",
    )
    return _normalize_issue_detail(payload)


def assign_tracked_issue(
    db: Session,
    *,
    actor: User,
    tracked_issue_id: str,
    assignee_ids: list[int] | None = None,
) -> dict:
    _require_delivery_issue_write_access(actor=actor)
    _, project_id, issue_iid = _resolve_tracked_issue_reference(db, tracked_issue_id=tracked_issue_id)
    normalized_assignee_ids = _normalize_assignee_ids(assignee_ids)
    payload = _request_gitlab_issue_mutation(
        method="PUT",
        project_id=project_id,
        issue_iid=issue_iid,
        body={"assignee_ids": normalized_assignee_ids},
        action_label="GitLab issue assign failed",
    )
    return _normalize_issue_detail(payload)


def add_tracked_issue_comment(
    db: Session,
    *,
    actor: User,
    tracked_issue_id: str,
    body: str,
    internal: bool = False,
) -> dict:
    _require_delivery_issue_write_access(actor=actor)
    _, project_id, issue_iid = _resolve_tracked_issue_reference(db, tracked_issue_id=tracked_issue_id)
    normalized_body = (body or "").strip()
    if not normalized_body:
        raise ValidationError("Comment body is required")
    payload_body = {"body": normalized_body}
    if internal:
        payload_body["internal"] = True
    payload = _request_gitlab_issue_mutation(
        method="POST",
        project_id=project_id,
        issue_iid=issue_iid,
        body=payload_body,
        action_label="GitLab issue comment failed",
        endpoint_suffix="/notes",
    )
    return _normalize_issue_note(payload)


def serialize_tracked_issue(row: GitLabTrackedIssue) -> dict:
    assignees = row.target_assignees or []
    assignee_name = assignees[0]["name"] if assignees and isinstance(assignees[0], dict) else None
    return {
        "id": row.id,
        "delivery_issue_id": row.delivery_issue_id,
        "delivery_issue_iid": row.delivery_issue_iid,
        "delivery_title": row.delivery_title,
        "delivery_url": row.delivery_url,
        "delivery_state": row.delivery_state,
        "delivery_labels": row.delivery_labels or [],
        "delivery_created_at": row.delivery_created_at,
        "delivery_updated_at": row.delivery_updated_at,
        "delivery_closed_at": row.delivery_closed_at,
        "target_project_id": row.target_project_id,
        "target_project_name": row.target_project_name,
        "target_team_name": row.target_team_name,
        "target_issue_id": row.target_issue_id,
        "target_issue_iid": row.target_issue_iid,
        "target_url": row.target_url,
        "target_state": row.target_state,
        "target_labels": row.target_labels or [],
        "target_assignees": assignees,
        "target_assignee": assignee_name,
        "target_updated_at": row.target_updated_at,
        "activity_source": row.activity_source,
        "activity_comment_count": row.activity_comment_count,
        "target_missing": row.target_missing,
        "resolution_source": row.resolution_source,
        "sync_status": row.sync_status,
        "sync_error": row.sync_error,
        "last_synced_at": row.last_synced_at,
        "has_manual_mapping": bool(row.manual_mapping_id),
    }


def serialize_sync_run(row: GitLabIssueSyncRun) -> dict:
    return {
        "id": row.id,
        "status": row.status,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "total_issues": row.total_issues,
        "resolved_targets": row.resolved_targets,
        "missing_targets": row.missing_targets,
        "failed_targets": row.failed_targets,
        "manual_mappings_used": row.manual_mappings_used,
        "moved_to_resolutions": row.moved_to_resolutions,
        "note_resolutions": row.note_resolutions,
        "error_message": row.error_message,
    }


def sync_delivery_issues(db: Session, *, triggered_by: str = "manual") -> GitLabIssueSyncRun:
    lock_acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": SYNC_ADVISORY_LOCK_ID}).scalar())
    if not lock_acquired:
        run = GitLabIssueSyncRun(
            id=new_id(),
            status="skipped",
            started_at=_utcnow(),
            finished_at=_utcnow(),
            error_message="Another delivery sync run is already in progress",
        )
        db.add(run)
        db.flush()
        return run

    run = GitLabIssueSyncRun(id=new_id(), status="running", started_at=_utcnow())
    db.add(run)
    db.flush()

    try:
        if not _sync_configured():
            run.status = "error"
            run.finished_at = _utcnow()
            run.error_message = "GitLab delivery tracking is not configured"
            return run

        target_teams = _target_team_map()
        project_cache: dict[str, dict[str, str]] = {}
        client = GitLabReadOnlyClient(base_url=settings.gitlab_base_url, token=str(settings.gitlab_token))
        try:
            issues = client.list_project_issues(str(settings.gitlab_delivery_project_id), state="all")
            run.total_issues = len(issues)
            for payload in issues:
                try:
                    outcome = _sync_delivery_issue(
                        db,
                        client=client,
                        payload=payload,
                        target_teams=target_teams,
                        project_cache=project_cache,
                    )
                except Exception as exc:  # pragma: no cover - defensive guard
                    run.failed_targets += 1
                    logger.warning("delivery issue sync failed: trigger=%s error=%s", triggered_by, exc)
                    continue
                if outcome.status == "ok":
                    run.resolved_targets += 1
                elif outcome.status == "target_missing":
                    run.missing_targets += 1
                else:
                    run.failed_targets += 1
                if outcome.used_manual_mapping:
                    run.manual_mappings_used += 1
                if outcome.used_moved_to:
                    run.moved_to_resolutions += 1
                if outcome.used_note_fallback:
                    run.note_resolutions += 1
            run.status = _summarize_run_status(run)
        except GitLabApiError as exc:
            run.status = "error"
            run.error_message = str(exc)
            logger.warning("gitlab delivery sync blocked by API: %s", exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            run.status = "error"
            run.error_message = str(exc)
            logger.exception("gitlab delivery sync crashed unexpectedly")
        finally:
            run.finished_at = _utcnow()
            client.close()
    finally:
        db.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": SYNC_ADVISORY_LOCK_ID})
    return run


def set_manual_mapping(db: Session, *, tracked_issue_id: str, target_url: str, actor: User) -> GitLabTrackedIssue:
    tracked = db.get(GitLabTrackedIssue, tracked_issue_id)
    if not tracked:
        raise NotFoundError("Tracked issue not found")
    previous_snapshot = _tracked_issue_alert_snapshot(tracked)

    if actor.kind != "internal":
        raise ValidationError("Only internal users can update manual issue mapping")

    if not settings.gitlab_token:
        raise ValidationError("GITLAB_TOKEN is not configured")

    project_path, issue_iid = _parse_issue_url(target_url)
    client = GitLabReadOnlyClient(base_url=settings.gitlab_base_url, token=str(settings.gitlab_token))
    project_cache: dict[str, dict[str, str]] = {}
    target_teams = _target_team_map()
    try:
        project = _resolve_project(client, project_path, project_cache)
        mapping = db.scalar(
            select(GitLabIssueManualMapping).where(
                GitLabIssueManualMapping.delivery_project_id == tracked.delivery_project_id,
                GitLabIssueManualMapping.delivery_issue_iid == tracked.delivery_issue_iid,
            )
        )
        if mapping is None:
            mapping = GitLabIssueManualMapping(
                id=new_id(),
                delivery_project_id=tracked.delivery_project_id,
                delivery_issue_iid=tracked.delivery_issue_iid,
                created_by_user_id=actor.id,
            )
            db.add(mapping)
        mapping.target_url = target_url.strip()
        mapping.target_project_id = project["id"]
        mapping.target_project_name = project["name"]
        mapping.target_issue_iid = issue_iid
        mapping.updated_at = _utcnow()
        db.flush()

        tracked.manual_mapping_id = mapping.id
        tracked.updated_at = _utcnow()
        tracked.last_synced_at = _utcnow()
        tracked.resolution_source = "manual"

        try:
            mapped_issue = client.get_project_issue(project["id"], issue_iid)
            target_issue, _, _, chain_error = _resolve_terminal_issue(
                client,
                start_issue=mapped_issue,
                project_cache=project_cache,
            )
            _apply_target_fields(
                tracked,
                target_issue=target_issue,
                source="manual",
                target_teams=target_teams,
                client=client,
                project_cache=project_cache,
            )
            _apply_activity_fields(tracked, issue_payload=target_issue, source="target")
            if chain_error:
                tracked.sync_error = chain_error
            else:
                tracked.sync_error = None
            tracked.sync_status = "ok"
            tracked.target_missing = False
        except GitLabApiError as exc:
            _clear_target_fields(tracked)
            if exc.status_code == 404:
                tracked.sync_status = "target_missing"
                tracked.target_missing = True
            else:
                tracked.sync_status = "error"
                tracked.target_missing = False
            tracked.sync_error = f"Manual mapping lookup failed: {exc}"
    finally:
        client.close()

    _emit_delivery_alert_if_needed(
        db,
        tracked=tracked,
        previous_snapshot=previous_snapshot,
        is_new=False,
    )
    return tracked


def _sync_delivery_issue(
    db: Session,
    *,
    client: GitLabReadOnlyClient,
    payload: dict,
    target_teams: dict[str, str],
    project_cache: dict[str, dict[str, str]],
) -> IssueSyncOutcome:
    delivery_project_id = str(payload.get("project_id") or settings.gitlab_delivery_project_id or "")
    delivery_issue_id = _string_or_none(payload.get("id"))
    delivery_issue_iid = str(payload.get("iid") or "")
    if not delivery_project_id or not delivery_issue_iid:
        raise ValidationError("Delivery issue payload is missing project_id or iid")

    tracked = db.scalar(
        select(GitLabTrackedIssue).where(
            GitLabTrackedIssue.delivery_project_id == delivery_project_id,
            GitLabTrackedIssue.delivery_issue_iid == delivery_issue_iid,
        )
    )
    if tracked is None:
        tracked = _find_reusable_tracked_issue(
            db,
            delivery_project_id=delivery_project_id,
            delivery_issue_iid=delivery_issue_iid,
            delivery_issue_id=delivery_issue_id,
        )
    is_new = tracked is None
    previous_snapshot = None if tracked is None else _tracked_issue_alert_snapshot(tracked)
    if tracked is None:
        tracked = GitLabTrackedIssue(
            id=new_id(),
            delivery_project_id=delivery_project_id,
            delivery_issue_iid=delivery_issue_iid,
            delivery_title=str(payload.get("title") or f"Delivery #{delivery_issue_iid}"),
            delivery_url=str(payload.get("web_url") or ""),
            delivery_state=str(payload.get("state") or "opened"),
        )
        db.add(tracked)

    _apply_delivery_fields(tracked, payload=payload, delivery_project_id=delivery_project_id)

    mapping = db.scalar(
        select(GitLabIssueManualMapping).where(
            GitLabIssueManualMapping.delivery_project_id == delivery_project_id,
            GitLabIssueManualMapping.delivery_issue_iid == delivery_issue_iid,
        )
    )
    tracked.manual_mapping_id = mapping.id if mapping else None

    resolution = _resolve_target_issue(
        client=client,
        delivery_payload=payload,
        mapping=mapping,
        project_cache=project_cache,
    )

    tracked.last_synced_at = _utcnow()
    tracked.updated_at = _utcnow()
    expected_sync_status = _expected_sync_status(resolution)

    if expected_sync_status == "ok" and resolution.issue is not None:
        _apply_target_fields(
            tracked,
            target_issue=resolution.issue,
            source=resolution.source,
            target_teams=target_teams,
            client=client,
            project_cache=project_cache,
        )
        _apply_activity_fields(tracked, issue_payload=resolution.issue, source="target")
        tracked.sync_status = "ok"
        tracked.sync_error = resolution.fatal_error
        tracked.target_missing = False
        return _sync_outcome_with_alert(
            db,
            tracked=tracked,
            previous_snapshot=previous_snapshot,
            is_new=is_new,
            outcome=IssueSyncOutcome(
                status="ok",
                used_manual_mapping=resolution.used_manual_mapping,
                used_moved_to=resolution.used_moved_to,
                used_note_fallback=resolution.used_note_fallback,
            ),
        )

    _clear_target_fields(tracked)
    if expected_sync_status == "error":
        _apply_activity_fields(tracked, issue_payload=payload, source="delivery")
        tracked.sync_status = "error"
        tracked.sync_error = resolution.fatal_error
        tracked.target_missing = False
        tracked.resolution_source = "error"
        return _sync_outcome_with_alert(
            db,
            tracked=tracked,
            previous_snapshot=previous_snapshot,
            is_new=is_new,
            outcome=IssueSyncOutcome(status="error"),
        )

    if expected_sync_status == "in_delivery":
        _apply_activity_fields(tracked, issue_payload=payload, source="delivery")
        tracked.sync_status = "in_delivery"
        tracked.sync_error = None
        tracked.target_missing = False
        tracked.resolution_source = "delivery"
        tracked.target_team_name = "Delivery"
        return _sync_outcome_with_alert(
            db,
            tracked=tracked,
            previous_snapshot=previous_snapshot,
            is_new=is_new,
            outcome=IssueSyncOutcome(
                status="ok",
                used_manual_mapping=resolution.used_manual_mapping,
                used_moved_to=resolution.used_moved_to,
                used_note_fallback=resolution.used_note_fallback,
            ),
        )

    _apply_activity_fields(tracked, issue_payload=payload, source="delivery")
    tracked.sync_status = "target_missing"
    tracked.sync_error = "Target issue could not be resolved automatically"
    tracked.target_missing = True
    tracked.resolution_source = "target_missing"
    return _sync_outcome_with_alert(
        db,
        tracked=tracked,
        previous_snapshot=previous_snapshot,
        is_new=is_new,
        outcome=IssueSyncOutcome(
            status="target_missing",
            used_manual_mapping=resolution.used_manual_mapping,
            used_moved_to=resolution.used_moved_to,
            used_note_fallback=resolution.used_note_fallback,
        ),
    )


def _find_reusable_tracked_issue(
    db: Session,
    *,
    delivery_project_id: str,
    delivery_issue_iid: str,
    delivery_issue_id: str | None,
) -> GitLabTrackedIssue | None:
    if not delivery_issue_id:
        return None
    candidates = db.scalars(
        select(GitLabTrackedIssue).where(
            GitLabTrackedIssue.delivery_project_id == delivery_project_id,
            GitLabTrackedIssue.delivery_issue_iid != delivery_issue_iid,
            GitLabTrackedIssue.target_issue_id == delivery_issue_id,
        )
    ).all()
    if not candidates:
        return None
    return sorted(candidates, key=_tracked_issue_dedupe_score, reverse=True)[0]


def _expected_sync_status(resolution: TargetResolution) -> str:
    if resolution.issue is not None:
        return "ok"
    if resolution.fatal_error:
        return "error"
    if not resolution.has_target_hint:
        return "in_delivery"
    return "target_missing"


def _sync_outcome_with_alert(
    db: Session,
    *,
    tracked: GitLabTrackedIssue,
    previous_snapshot: dict[str, object] | None,
    is_new: bool,
    outcome: IssueSyncOutcome,
) -> IssueSyncOutcome:
    _emit_delivery_alert_if_needed(
        db,
        tracked=tracked,
        previous_snapshot=previous_snapshot,
        is_new=is_new,
    )
    return outcome


def _emit_delivery_alert_if_needed(
    db: Session,
    *,
    tracked: GitLabTrackedIssue,
    previous_snapshot: dict[str, object] | None,
    is_new: bool,
) -> None:
    current_snapshot = _tracked_issue_alert_snapshot(tracked)
    payload = _build_delivery_alert_payload(
        tracked,
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
        is_new=is_new,
    )
    if payload is None:
        return
    if tracked in db.new:
        # Persist newly tracked issue first so alert FK always points to an existing row.
        db.flush([tracked])
    db.add(
        GitLabDeliveryAlert(
            id=new_id(),
            tracked_issue_id=tracked.id,
            delivery_issue_iid=tracked.delivery_issue_iid,
            delivery_title=tracked.delivery_title,
            delivery_url=tracked.delivery_url,
            target_url=tracked.target_url,
            alert_kind=payload["kind"],
            message=payload["message"],
            changes={"changes": payload["changes"]},
            created_at=_utcnow(),
        )
    )


def _build_delivery_alert_payload(
    tracked: GitLabTrackedIssue,
    *,
    previous_snapshot: dict[str, object] | None,
    current_snapshot: dict[str, object],
    is_new: bool,
) -> dict[str, object] | None:
    if previous_snapshot is None:
        if not is_new:
            return None
        return {
            "kind": "tracked",
            "message": "New delivery issue started tracking.",
            "changes": [],
        }

    changes = _tracked_issue_alert_changes(previous_snapshot, current_snapshot)
    if _activity_markers_uninitialized(previous_snapshot):
        changes = [
            change
            for change in changes
            if change["field"] not in {"activity_comment_count", "activity_description_digest"}
        ]
    if not changes:
        return None
    kind, message = _delivery_alert_kind_and_message(
        tracked,
        changes,
        previous_snapshot=previous_snapshot,
        current_snapshot=current_snapshot,
    )
    return {"kind": kind, "message": message, "changes": changes}


def _tracked_issue_alert_snapshot(tracked: GitLabTrackedIssue) -> dict[str, object]:
    last_gitlab_update = tracked.target_updated_at or tracked.delivery_updated_at
    return {
        "delivery_title": tracked.delivery_title or "",
        "delivery_state": tracked.delivery_state or "",
        "delivery_labels": tuple(_normalize_labels(tracked.delivery_labels)),
        "target_issue_iid": tracked.target_issue_iid or "",
        "target_state": tracked.target_state or "",
        "target_team_name": tracked.target_team_name or "",
        "target_url": tracked.target_url or "",
        "target_labels": tuple(_normalize_labels(tracked.target_labels)),
        "target_assignees": tuple(_assignee_names(tracked)),
        "activity_source": tracked.activity_source or "",
        "activity_comment_count": tracked.activity_comment_count if tracked.activity_comment_count is not None else "",
        "activity_description_digest": tracked.activity_description_digest or "",
        "sync_status": tracked.sync_status or "",
        "resolution_source": tracked.resolution_source or "",
        "target_missing": bool(tracked.target_missing),
        "sync_error": tracked.sync_error or "",
        "last_gitlab_update": last_gitlab_update.isoformat() if isinstance(last_gitlab_update, datetime) else "",
    }


def _tracked_issue_alert_changes(previous_snapshot: dict[str, object], current_snapshot: dict[str, object]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for field, label in ALERT_FIELD_LABELS:
        previous_value = previous_snapshot.get(field)
        current_value = current_snapshot.get(field)
        if previous_value == current_value:
            continue
        before_text = _alert_value_text(previous_value)
        after_text = _alert_value_text(current_value)
        if field == "activity_description_digest":
            before_text = "edited" if before_text else ""
            after_text = "edited"
        elif field == "activity_comment_count":
            before_text = before_text or "0"
            after_text = after_text or "0"
        changes.append(
            {
                "field": field,
                "label": label,
                "before": before_text,
                "after": after_text,
            }
        )
    return changes


def _delivery_alert_kind_and_message(
    tracked: GitLabTrackedIssue,
    changes: list[dict[str, str]],
    *,
    previous_snapshot: dict[str, object],
    current_snapshot: dict[str, object],
) -> tuple[str, str]:
    changed_fields = {change["field"] for change in changes}
    if "sync_status" in changed_fields:
        if tracked.sync_status == "target_missing":
            return "target_missing", "Target mapping is missing and needs attention."
        if tracked.sync_status == "error":
            return "sync_error", "Delivery tracking sync reported an error."
        if tracked.sync_status == "ok":
            return "sync_status", "Delivery tracking sync status returned to synced."
        return "sync_status", f"Sync status changed to {tracked.sync_status or 'unknown'}."

    if {"target_issue_iid", "target_url", "target_team_name"} & changed_fields:
        if tracked.target_issue_iid:
            return "reassigned", f"Ticket moved to team id {tracked.target_issue_iid}."
        return "reassigned", "Ticket target assignment changed."

    source_changed = previous_snapshot.get("activity_source") != current_snapshot.get("activity_source")
    if "target_assignees" in changed_fields:
        return "assignee_changed", "Ticket assignee changed."

    comment_changed = "activity_comment_count" in changed_fields
    description_changed = "activity_description_digest" in changed_fields
    comment_delta = _activity_comment_delta(previous_snapshot, current_snapshot)

    if not source_changed and comment_changed and description_changed:
        if comment_delta and comment_delta > 0:
            suffix = "comment" if comment_delta == 1 else "comments"
            return "comment_and_description", f"{comment_delta} new {suffix} added and description was edited."
        return "comment_and_description", "Ticket comments changed and description was edited."

    if not source_changed and comment_changed:
        if comment_delta and comment_delta > 0:
            suffix = "comment" if comment_delta == 1 else "comments"
            return "comment_added", f"{comment_delta} new {suffix} added."
        return "comment_activity", "Ticket comments changed."

    if not source_changed and description_changed:
        return "description_edited", "Ticket description was edited."

    if {"target_state", "delivery_state"} & changed_fields:
        state = tracked.target_state or tracked.delivery_state or "unknown"
        return "state_changed", f"Ticket state changed to {state}."

    if changed_fields == {"last_gitlab_update"}:
        return "activity", "Ticket has new GitLab activity (comment or update)."

    return "updated", "Tracked ticket details changed in GitLab."


def _activity_comment_delta(previous_snapshot: dict[str, object], current_snapshot: dict[str, object]) -> int | None:
    previous_count = _int_or_none(previous_snapshot.get("activity_comment_count"))
    current_count = _int_or_none(current_snapshot.get("activity_comment_count"))
    if previous_count is None or current_count is None:
        return None
    return current_count - previous_count


def _activity_markers_uninitialized(snapshot: dict[str, object]) -> bool:
    if _string_or_none(snapshot.get("activity_source")):
        return False
    if _string_or_none(snapshot.get("activity_description_digest")):
        return False
    return _int_or_none(snapshot.get("activity_comment_count")) is None


def _alert_value_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, tuple):
        chunks = []
        for item in value:
            text = _alert_value_text(item)
            if text:
                chunks.append(text)
        return ", ".join(chunks)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _resolve_target_issue(
    *,
    client: GitLabReadOnlyClient,
    delivery_payload: dict,
    mapping: GitLabIssueManualMapping | None,
    project_cache: dict[str, dict[str, str]],
) -> TargetResolution:
    delivery_project_id = _string_or_none(delivery_payload.get("project_id")) or _string_or_none(settings.gitlab_delivery_project_id) or ""
    delivery_issue_iid = _string_or_none(delivery_payload.get("iid")) or ""
    fatal_error: str | None = None
    has_target_hint = bool(mapping and mapping.target_project_id and mapping.target_issue_iid)

    if mapping and mapping.target_project_id and mapping.target_issue_iid:
        try:
            manual_issue = client.get_project_issue(mapping.target_project_id, mapping.target_issue_iid)
            issue, used_moved_to, used_note_fallback, chain_error = _resolve_terminal_issue(
                client,
                start_issue=manual_issue,
                project_cache=project_cache,
            )
            return TargetResolution(
                issue=issue,
                source="manual",
                used_manual_mapping=True,
                used_moved_to=used_moved_to,
                used_note_fallback=used_note_fallback,
                has_target_hint=True,
                fatal_error=chain_error,
            )
        except GitLabApiError as exc:
            if not _is_recoverable_link_error(exc):
                fatal_error = f"Manual mapping lookup failed: {exc}"
            logger.info(
                "manual mapping could not resolve issue delivery_iid=%s error=%s",
                delivery_issue_iid,
                exc,
            )

    candidate_issue: dict | None = None
    source = "none"
    used_moved_to = False
    used_note_fallback = False

    moved_to_id = _string_or_none(delivery_payload.get("moved_to_id"))
    if moved_to_id:
        has_target_hint = True
        try:
            candidate_issue = client.get_global_issue(moved_to_id)
            source = "moved_to_id"
            used_moved_to = True
        except GitLabApiError as exc:
            if not _is_recoverable_link_error(exc):
                fatal_error = f"moved_to_id lookup failed: {exc}"

    if candidate_issue is None and delivery_project_id and delivery_issue_iid:
        note_target = _resolve_target_from_system_notes(
            client,
            delivery_project_id=delivery_project_id,
            delivery_issue_iid=delivery_issue_iid,
            project_cache=project_cache,
        )
        if note_target is not None:
            has_target_hint = True
            project_id, issue_iid = note_target
            try:
                candidate_issue = client.get_project_issue(project_id, issue_iid)
                source = "system_note"
                used_note_fallback = True
            except GitLabApiError as exc:
                if not _is_recoverable_link_error(exc):
                    fatal_error = f"system note lookup failed: {exc}"

    if candidate_issue is None:
        return TargetResolution(
            issue=None,
            source="none",
            used_manual_mapping=False,
            used_moved_to=used_moved_to,
            used_note_fallback=used_note_fallback,
            has_target_hint=has_target_hint,
            fatal_error=fatal_error,
        )

    terminal_issue, chained_moved, chained_note, chain_error = _resolve_terminal_issue(
        client,
        start_issue=candidate_issue,
        project_cache=project_cache,
    )
    return TargetResolution(
        issue=terminal_issue,
        source=source,
        used_manual_mapping=False,
        used_moved_to=used_moved_to or chained_moved,
        used_note_fallback=used_note_fallback or chained_note,
        has_target_hint=has_target_hint,
        fatal_error=fatal_error or chain_error,
    )


def _resolve_terminal_issue(
    client: GitLabReadOnlyClient,
    *,
    start_issue: dict,
    project_cache: dict[str, dict[str, str]],
    max_hops: int = 20,
) -> tuple[dict, bool, bool, str | None]:
    current_issue = start_issue
    visited: set[tuple[str | None, str | None]] = set()
    used_moved_to = False
    used_note_fallback = False
    fatal_error: str | None = None

    for _ in range(max_hops):
        issue_key = (_string_or_none(current_issue.get("project_id")), _string_or_none(current_issue.get("iid")))
        if issue_key in visited:
            fatal_error = "Issue move chain contains a cycle"
            break
        visited.add(issue_key)

        next_issue, next_source, next_error = _resolve_next_issue_in_chain(
            client,
            issue=current_issue,
            project_cache=project_cache,
        )
        if next_issue is None:
            if next_error:
                fatal_error = next_error
            break
        if next_source == "moved_to_id":
            used_moved_to = True
        elif next_source == "system_note":
            used_note_fallback = True
        current_issue = next_issue
    else:
        fatal_error = "Issue move chain exceeds maximum hop count"

    return current_issue, used_moved_to, used_note_fallback, fatal_error


def _resolve_next_issue_in_chain(
    client: GitLabReadOnlyClient,
    *,
    issue: dict,
    project_cache: dict[str, dict[str, str]],
) -> tuple[dict | None, str | None, str | None]:
    fallback_error: str | None = None
    moved_to_id = _string_or_none(issue.get("moved_to_id"))
    if moved_to_id:
        try:
            return client.get_global_issue(moved_to_id), "moved_to_id", None
        except GitLabApiError as exc:
            if not _is_recoverable_link_error(exc):
                fallback_error = f"moved_to_id lookup failed: {exc}"

    project_id = _string_or_none(issue.get("project_id"))
    issue_iid = _string_or_none(issue.get("iid"))
    if project_id and issue_iid:
        note_target = _resolve_target_from_system_notes(
            client,
            delivery_project_id=project_id,
            delivery_issue_iid=issue_iid,
            project_cache=project_cache,
        )
        if note_target is not None:
            target_project_id, target_issue_iid = note_target
            try:
                return client.get_project_issue(target_project_id, target_issue_iid), "system_note", None
            except GitLabApiError as exc:
                if not _is_recoverable_link_error(exc):
                    fallback_error = f"system note lookup failed: {exc}"

    return None, None, fallback_error


def _is_recoverable_link_error(exc: GitLabApiError) -> bool:
    return exc.status_code in {403, 404}


def _apply_delivery_fields(tracked: GitLabTrackedIssue, *, payload: dict, delivery_project_id: str) -> None:
    tracked.delivery_project_id = delivery_project_id
    tracked.delivery_issue_id = _string_or_none(payload.get("id"))
    tracked.delivery_issue_iid = _string_or_none(payload.get("iid")) or tracked.delivery_issue_iid
    tracked.delivery_title = str(payload.get("title") or tracked.delivery_title or "")
    tracked.delivery_url = str(payload.get("web_url") or tracked.delivery_url or "")
    tracked.delivery_state = str(payload.get("state") or tracked.delivery_state or "opened")
    tracked.delivery_labels = _normalize_labels(payload.get("labels"))
    tracked.delivery_created_at = _parse_gitlab_datetime(payload.get("created_at"))
    tracked.delivery_updated_at = _parse_gitlab_datetime(payload.get("updated_at"))
    tracked.delivery_closed_at = _parse_gitlab_datetime(payload.get("closed_at"))
    tracked.moved_to_id = _string_or_none(payload.get("moved_to_id"))


def _apply_target_fields(
    tracked: GitLabTrackedIssue,
    *,
    target_issue: dict,
    source: str,
    target_teams: dict[str, str],
    client: GitLabReadOnlyClient,
    project_cache: dict[str, dict[str, str]],
) -> None:
    project_id = _string_or_none(target_issue.get("project_id"))
    project_name = ""
    if project_id:
        try:
            project_name = _resolve_project(client, project_id, project_cache)["name"]
        except GitLabApiError:
            project_name = project_id
    issue_id = _string_or_none(target_issue.get("id"))
    issue_iid = _string_or_none(target_issue.get("iid"))
    tracked.resolution_source = source
    tracked.target_project_id = project_id
    tracked.target_project_name = project_name or None
    tracked.target_team_name = target_teams.get(project_id or "", project_name or project_id or None)
    tracked.target_issue_id = issue_id
    tracked.target_issue_iid = issue_iid
    tracked.target_url = _string_or_none(target_issue.get("web_url"))
    tracked.target_state = _string_or_none(target_issue.get("state"))
    tracked.target_labels = _normalize_labels(target_issue.get("labels"))
    tracked.target_assignees = _normalize_assignees(target_issue.get("assignees"))
    tracked.target_updated_at = _parse_gitlab_datetime(target_issue.get("updated_at"))


def _apply_activity_fields(tracked: GitLabTrackedIssue, *, issue_payload: dict, source: str) -> None:
    tracked.activity_source = source
    tracked.activity_description_digest = _issue_description_digest(issue_payload)
    tracked.activity_comment_count = _issue_comment_count(issue_payload)


def _clear_target_fields(tracked: GitLabTrackedIssue) -> None:
    tracked.target_project_id = None
    tracked.target_project_name = None
    tracked.target_team_name = None
    tracked.target_issue_id = None
    tracked.target_issue_iid = None
    tracked.target_url = None
    tracked.target_state = None
    tracked.target_labels = None
    tracked.target_assignees = None
    tracked.target_updated_at = None


def _resolve_target_from_system_notes(
    client: GitLabReadOnlyClient,
    *,
    delivery_project_id: str,
    delivery_issue_iid: str,
    project_cache: dict[str, dict[str, str]],
) -> tuple[str, str] | None:
    try:
        notes = client.get_issue_notes(delivery_project_id, delivery_issue_iid)
    except GitLabApiError:
        return None
    for note in notes:
        if not note.get("system"):
            continue
        body = str(note.get("body") or "")
        for raw_url in ISSUE_URL_IN_TEXT_RE.findall(body):
            try:
                project_path, issue_iid = _parse_issue_url(raw_url)
                project = _resolve_project(client, project_path, project_cache)
                return project["id"], issue_iid
            except (ValidationError, GitLabApiError):
                continue
        match = MOVED_NOTE_RE.search(body)
        if match:
            project_path = match.group("project_path")
            issue_iid = match.group("issue_iid")
            try:
                project = _resolve_project(client, project_path, project_cache)
                return project["id"], issue_iid
            except GitLabApiError:
                continue
    return None


def _resolve_project(
    client: GitLabReadOnlyClient,
    project_id_or_path: str,
    project_cache: dict[str, dict[str, str]],
) -> dict[str, str]:
    cache_key = str(project_id_or_path).strip()
    if cache_key in project_cache:
        return project_cache[cache_key]
    payload = client.get_project(cache_key)
    project_id = _string_or_none(payload.get("id")) or cache_key
    name = str(payload.get("path_with_namespace") or payload.get("name") or project_id)
    value = {"id": project_id, "name": name}
    project_cache[cache_key] = value
    project_cache[project_id] = value
    return value


def _summarize_run_status(run: GitLabIssueSyncRun) -> str:
    if run.failed_targets > 0 and run.resolved_targets == 0 and run.missing_targets == 0:
        return "error"
    if run.failed_targets > 0:
        return "partial"
    return "ok"


def _tracked_issue_invariant_errors(row: GitLabTrackedIssue) -> list[str]:
    errors: list[str] = []
    if row.sync_status == "in_delivery":
        if row.target_missing:
            errors.append("in_delivery issue must not have target_missing=true")
        if row.target_project_id or row.target_issue_iid or row.target_url:
            errors.append("in_delivery issue must not keep target issue fields")
    if row.sync_status == "target_missing" and not row.target_missing:
        errors.append("target_missing issue must have target_missing=true")
    if row.sync_status == "ok" and row.target_missing:
        errors.append("ok issue must not have target_missing=true")
    if row.sync_status == "in_delivery" and row.resolution_source != "delivery":
        errors.append("in_delivery issue should have resolution_source=delivery")
    return errors


def _dedupe_tracked_issue_rows(rows: list[GitLabTrackedIssue]) -> list[GitLabTrackedIssue]:
    if not rows:
        return []
    by_delivery_issue_id = _index_tracked_rows_by_delivery_issue_id(rows)
    by_chain: dict[tuple[str, ...], GitLabTrackedIssue] = {}
    for row in rows:
        terminal_row = _resolve_delivery_chain_terminal_row(row, by_delivery_issue_id)
        chain_key = _tracked_issue_chain_key(terminal_row)
        current_chain_row = by_chain.get(chain_key)
        if current_chain_row is None or _tracked_issue_dedupe_score(terminal_row) > _tracked_issue_dedupe_score(current_chain_row):
            by_chain[chain_key] = terminal_row
    chosen: dict[tuple[str, ...], GitLabTrackedIssue] = {}
    for row in by_chain.values():
        dedupe_key = _tracked_issue_dedupe_key(row)
        current = chosen.get(dedupe_key)
        if current is None or _tracked_issue_dedupe_score(row) > _tracked_issue_dedupe_score(current):
            chosen[dedupe_key] = row
    return list(chosen.values())


def _index_tracked_rows_by_delivery_issue_id(rows: list[GitLabTrackedIssue]) -> dict[str, GitLabTrackedIssue]:
    indexed: dict[str, GitLabTrackedIssue] = {}
    for row in rows:
        issue_id = _string_or_none(getattr(row, "delivery_issue_id", None))
        if not issue_id:
            continue
        current = indexed.get(issue_id)
        if current is None or _tracked_issue_dedupe_score(row) > _tracked_issue_dedupe_score(current):
            indexed[issue_id] = row
    return indexed


def _resolve_delivery_chain_terminal_row(
    row: GitLabTrackedIssue,
    by_delivery_issue_id: dict[str, GitLabTrackedIssue],
    *,
    max_hops: int = 20,
) -> GitLabTrackedIssue:
    current = row
    visited: set[str] = set()
    for _ in range(max_hops):
        moved_to_id = _string_or_none(getattr(current, "moved_to_id", None))
        if not moved_to_id:
            break
        if moved_to_id in visited:
            break
        visited.add(moved_to_id)
        next_row = by_delivery_issue_id.get(moved_to_id)
        if next_row is None:
            break
        current = next_row
    return current


def _tracked_issue_chain_key(row: GitLabTrackedIssue) -> tuple[str, ...]:
    delivery_project_id = _string_or_none(getattr(row, "delivery_project_id", None)) or ""
    delivery_issue_id = _string_or_none(getattr(row, "delivery_issue_id", None))
    if delivery_issue_id:
        return ("delivery_chain_id", delivery_project_id, delivery_issue_id)
    delivery_issue_iid = _string_or_none(getattr(row, "delivery_issue_iid", None))
    if delivery_issue_iid:
        return ("delivery_chain_iid", delivery_project_id, delivery_issue_iid)
    fallback_id = _string_or_none(getattr(row, "id", None))
    return ("delivery_chain_row", fallback_id or "")


def _tracked_issue_dedupe_key(row: GitLabTrackedIssue) -> tuple[str, ...]:
    terminal_issue_id = _tracked_issue_terminal_issue_id(row)
    if terminal_issue_id:
        return ("terminal_issue_id", terminal_issue_id)

    target_project_id = _string_or_none(getattr(row, "target_project_id", None))
    target_issue_iid = _string_or_none(getattr(row, "target_issue_iid", None))
    if target_project_id and target_issue_iid:
        return ("target_issue", target_project_id, target_issue_iid)

    moved_to_id = _string_or_none(getattr(row, "moved_to_id", None))
    if moved_to_id:
        return ("moved_to_id", moved_to_id)

    delivery_project_id = _string_or_none(getattr(row, "delivery_project_id", None))
    delivery_issue_iid = _string_or_none(getattr(row, "delivery_issue_iid", None))
    if delivery_project_id or delivery_issue_iid:
        return ("delivery_issue", delivery_project_id or "", delivery_issue_iid or "")

    fallback_id = _string_or_none(getattr(row, "id", None))
    return ("row_id", fallback_id or "")


def _tracked_issue_dedupe_score(row: GitLabTrackedIssue) -> tuple[object, ...]:
    terminal_issue_id = _tracked_issue_terminal_issue_id(row)
    delivery_issue_id = _string_or_none(getattr(row, "delivery_issue_id", None))
    is_terminal_delivery_row = bool(terminal_issue_id and delivery_issue_id and terminal_issue_id == delivery_issue_id)
    delivery_state = (_string_or_none(getattr(row, "delivery_state", None)) or "").lower()
    return (
        1 if is_terminal_delivery_row else 0,
        _sync_status_priority(_string_or_none(getattr(row, "sync_status", None))),
        _datetime_sort_key(getattr(row, "target_updated_at", None)),
        _datetime_sort_key(getattr(row, "delivery_updated_at", None)),
        _datetime_sort_key(getattr(row, "last_synced_at", None)),
        _datetime_sort_key(getattr(row, "updated_at", None)),
        _datetime_sort_key(getattr(row, "created_at", None)),
        1 if delivery_state != "closed" else 0,
        _string_or_none(getattr(row, "delivery_issue_iid", None)) or "",
        _string_or_none(getattr(row, "id", None)) or "",
    )


def _tracked_issue_terminal_issue_id(row: GitLabTrackedIssue) -> str | None:
    return _string_or_none(getattr(row, "target_issue_id", None)) or _string_or_none(getattr(row, "delivery_issue_id", None))


def _sync_status_priority(value: str | None) -> int:
    if value == "ok":
        return 4
    if value == "in_delivery":
        return 3
    if value == "target_missing":
        return 2
    if value == "error":
        return 1
    return 0


def _datetime_sort_key(value: datetime | None) -> float:
    if not isinstance(value, datetime):
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _safe_iid_sort(value: str | None) -> tuple[int, str]:
    text = (value or "").strip()
    if text.isdigit():
        return int(text), ""
    return 10**9, text


def _append_check_finding(
    findings: list[dict],
    *,
    issue_iid: str | None,
    code: str,
    message: str,
    expected: object | None = None,
    actual: object | None = None,
) -> None:
    if len(findings) >= CHECK_FINDINGS_LIMIT:
        return
    finding = {
        "delivery_issue_iid": issue_iid,
        "code": code,
        "message": message,
    }
    if expected is not None:
        finding["expected"] = expected
    if actual is not None:
        finding["actual"] = actual
    findings.append(finding)


def _sort_tracked_issue_rows(
    rows: list[GitLabTrackedIssue],
    *,
    sort_by: str,
    sort_direction: str,
) -> list[GitLabTrackedIssue]:
    descending = sort_direction == "desc"

    def compare(left: GitLabTrackedIssue, right: GitLabTrackedIssue) -> int:
        return _compare_tracked_issue_rows(left, right, sort_by=sort_by, descending=descending)

    return sorted(rows, key=cmp_to_key(compare))


def _compare_tracked_issue_rows(
    left: GitLabTrackedIssue,
    right: GitLabTrackedIssue,
    *,
    sort_by: str,
    descending: bool,
) -> int:
    compared = _compare_nullable_values(
        _tracked_issue_sort_value(left, sort_by),
        _tracked_issue_sort_value(right, sort_by),
    )
    if compared == 0:
        compared = _compare_nullable_values(
            _tracked_issue_sort_value(left, "delivery_issue"),
            _tracked_issue_sort_value(right, "delivery_issue"),
        )
    return -compared if descending else compared


def _compare_nullable_values(left: object, right: object) -> int:
    left_empty = _is_empty_sort_value(left)
    right_empty = _is_empty_sort_value(right)
    if left_empty and right_empty:
        return 0
    if left_empty:
        return 1
    if right_empty:
        return -1
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _is_empty_sort_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, tuple):
        return all(_is_empty_sort_value(item) for item in value)
    return False


def _tracked_issue_sort_value(row: GitLabTrackedIssue, sort_by: str) -> object:
    if sort_by == "delivery_issue":
        iid_text = _string_or_none(row.delivery_issue_iid) or ""
        if iid_text.isdigit():
            return (int(iid_text), "", _string_or_none(row.delivery_title) or "")
        return (10**9, iid_text, _string_or_none(row.delivery_title) or "")
    if sort_by == "ticket_id":
        return _safe_iid_sort(row.delivery_issue_iid)
    if sort_by == "current_state":
        return (_string_or_none(row.target_state) or _string_or_none(row.delivery_state) or "").lower()
    if sort_by == "target_team":
        return (_string_or_none(row.target_team_name) or "").lower()
    if sort_by == "target_issue_url":
        return (_string_or_none(row.target_issue_iid) or _string_or_none(row.target_url) or "").lower()
    if sort_by == "assignee":
        return (_first_assignee_name(row) or "").lower()
    if sort_by == "labels":
        return ",".join(_effective_labels(row)).lower()
    if sort_by == "sync_status":
        return (_string_or_none(row.sync_status) or "").lower()
    if sort_by == "last_gitlab_update":
        timestamp = row.target_updated_at or row.delivery_updated_at
        return timestamp.timestamp() if timestamp else None
    if sort_by == "delivery_url":
        return (_string_or_none(row.delivery_url) or "").lower()
    if sort_by == "resolution_source":
        return (_string_or_none(row.resolution_source) or "").lower()
    return (_string_or_none(row.delivery_issue_iid) or "").lower()


def _first_assignee_name(row: GitLabTrackedIssue) -> str | None:
    assignees = _assignee_names(row)
    if not assignees:
        return None
    return assignees[0]


def _assignee_names(row: GitLabTrackedIssue) -> list[str]:
    names: list[str] = []
    for assignee in _normalize_assignees(row.target_assignees):
        name = _string_or_none(assignee.get("name")) or _string_or_none(assignee.get("username"))
        if name:
            names.append(name)
    return names


def _effective_labels(row: GitLabTrackedIssue) -> list[str]:
    target_labels = _normalize_labels(row.target_labels)
    if target_labels:
        return target_labels
    return _normalize_labels(row.delivery_labels)


def _row_matches_assignee_filter(row: GitLabTrackedIssue, assignee: str) -> bool:
    expected = _string_or_none(assignee)
    if not expected:
        return True
    token = expected.lower()
    return any(token in name.lower() for name in _assignee_names(row))


def _row_matches_label_filter(row: GitLabTrackedIssue, label: str) -> bool:
    expected = _string_or_none(label)
    if not expected:
        return True
    token = expected.lower()
    return any(token in value.lower() for value in _effective_labels(row))


def _target_team_map() -> dict[str, str]:
    return {project_id: name for project_id, name in settings.gitlab_target_projects}


def _normalize_labels(raw: object) -> list[str]:
    labels: list[str] = []
    if not isinstance(raw, list):
        return labels
    for item in raw:
        if isinstance(item, str):
            labels.append(item)
        elif isinstance(item, dict):
            value = item.get("title") or item.get("name")
            if isinstance(value, str):
                labels.append(value)
    return labels


def _sanitize_issue_labels(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _string_or_none(item)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        labels.append(text)
    return labels


def _normalize_assignees(raw: object) -> list[dict]:
    assignees: list[dict] = []
    if not isinstance(raw, list):
        return assignees
    for item in raw:
        if not isinstance(item, dict):
            continue
        assignees.append(
            {
                "id": _string_or_none(item.get("id")),
                "username": _string_or_none(item.get("username")),
                "name": _string_or_none(item.get("name")),
                "web_url": _string_or_none(item.get("web_url")),
            }
        )
    return assignees


def _normalize_project_members(raw: object) -> list[dict]:
    deduped: dict[str, dict] = {}
    for item in _normalize_assignees(raw):
        member_id = _string_or_none(item.get("id"))
        if not member_id:
            continue
        deduped[member_id] = item
    return sorted(
        deduped.values(),
        key=lambda member: (
            (_string_or_none(member.get("name")) or _string_or_none(member.get("username")) or "").casefold(),
            _string_or_none(member.get("id")) or "",
        ),
    )


def _normalize_assignee_ids(raw: list[int] | None) -> list[int]:
    if not raw:
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for item in raw:
        value = _int_or_none(item)
        if value is None or value <= 0 or value in seen:
            continue
        seen.add(value)
        ids.append(value)
    return ids


def _require_delivery_issue_write_access(*, actor: User) -> None:
    if actor.kind != "internal":
        raise ValidationError("Only internal users can modify delivery issues")
    if not settings.gitlab_base_url:
        raise ValidationError("GITLAB_BASE_URL is not configured")
    if not settings.gitlab_token:
        raise ValidationError("GITLAB_TOKEN is not configured")


def _resolve_tracked_issue_reference(db: Session, *, tracked_issue_id: str) -> tuple[GitLabTrackedIssue, str, str]:
    tracked = db.get(GitLabTrackedIssue, tracked_issue_id)
    if tracked is None:
        raise NotFoundError("Tracked issue not found")
    project_id = _string_or_none(tracked.target_project_id) or _string_or_none(tracked.delivery_project_id)
    issue_iid = _string_or_none(tracked.target_issue_iid) or _string_or_none(tracked.delivery_issue_iid)
    if not project_id or not issue_iid:
        raise ValidationError("Tracked issue is missing project or issue reference")
    return tracked, project_id, issue_iid


def _request_gitlab_issue_mutation(
    *,
    method: str,
    project_id: str,
    issue_iid: str,
    body: dict[str, object] | None,
    action_label: str,
    endpoint_suffix: str = "",
) -> dict:
    url = (
        f"{settings.gitlab_base_url.rstrip('/')}/api/v4/projects/"
        f"{quote_plus(str(project_id))}/issues/{quote_plus(str(issue_iid))}{endpoint_suffix}"
    )
    try:
        response = httpx.request(
            method=method,
            url=url,
            headers={"PRIVATE-TOKEN": str(settings.gitlab_token)},
            json=body,
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise ValidationError(f"{action_label}: request error") from exc
    if response.status_code >= 400:
        raise ValidationError(f"{action_label}: {_map_gitlab_error(response)}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValidationError(f"{action_label}: invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise ValidationError(f"{action_label}: invalid payload")
    return payload


def _normalize_issue_detail(raw: dict) -> dict:
    assignees = _normalize_assignees(raw.get("assignees"))
    if not assignees and isinstance(raw.get("assignee"), dict):
        assignees = _normalize_assignees([raw.get("assignee")])
    author_raw = raw.get("author")
    author = author_raw if isinstance(author_raw, dict) else {}
    milestone_raw = raw.get("milestone")
    milestone = None
    if isinstance(milestone_raw, dict):
        milestone = {
            "id": _string_or_none(milestone_raw.get("id")),
            "iid": _string_or_none(milestone_raw.get("iid")),
            "title": _string_or_none(milestone_raw.get("title")),
            "description": _string_or_none(milestone_raw.get("description")),
            "due_date": _string_or_none(milestone_raw.get("due_date")),
            "state": _string_or_none(milestone_raw.get("state")),
        }
        if not any(milestone.values()):
            milestone = None

    references = raw.get("references")
    references_dict = references if isinstance(references, dict) else {}
    return {
        "id": _string_or_none(raw.get("id")),
        "iid": _string_or_none(raw.get("iid")),
        "project_id": _string_or_none(raw.get("project_id")),
        "title": _string_or_none(raw.get("title")) or "",
        "description": _string_or_none(raw.get("description")) or "",
        "state": _string_or_none(raw.get("state")) or "opened",
        "issue_type": _string_or_none(raw.get("issue_type")) or "issue",
        "confidential": bool(raw.get("confidential")),
        "labels": _normalize_labels(raw.get("labels")),
        "assignees": assignees,
        "author": {
            "id": _string_or_none(author.get("id")),
            "username": _string_or_none(author.get("username")),
            "name": _string_or_none(author.get("name")),
            "avatar_url": _string_or_none(author.get("avatar_url")),
            "web_url": _string_or_none(author.get("web_url")),
        },
        "milestone": milestone,
        "due_date": _string_or_none(raw.get("due_date")),
        "created_at": _string_or_none(raw.get("created_at")),
        "updated_at": _string_or_none(raw.get("updated_at")),
        "closed_at": _string_or_none(raw.get("closed_at")),
        "web_url": _string_or_none(raw.get("web_url")),
        "reference": _string_or_none(references_dict.get("full") or references_dict.get("short")),
        "user_notes_count": _int_or_none(raw.get("user_notes_count")) or 0,
    }


def _normalize_issue_note(raw: dict) -> dict:
    author_raw = raw.get("author")
    author = author_raw if isinstance(author_raw, dict) else {}
    return {
        "id": _string_or_none(raw.get("id")),
        "body": _string_or_none(raw.get("body")) or "",
        "system": bool(raw.get("system")),
        "internal": bool(raw.get("internal")) or bool(raw.get("confidential")),
        "created_at": _string_or_none(raw.get("created_at")),
        "updated_at": _string_or_none(raw.get("updated_at")),
        "author": {
            "id": _string_or_none(author.get("id")),
            "username": _string_or_none(author.get("username")),
            "name": _string_or_none(author.get("name")),
            "avatar_url": _string_or_none(author.get("avatar_url")),
            "web_url": _string_or_none(author.get("web_url")),
        },
    }


def _normalize_due_date(value: str | None) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError("due_date must be in YYYY-MM-DD format") from exc
    return parsed.date().isoformat()


def _normalize_issue_type(value: str | None) -> str | None:
    text = _string_or_none(value)
    if not text:
        return None
    normalized = text.lower()
    if normalized not in CREATE_ISSUE_SUPPORTED_TYPES:
        raise ValidationError("Unsupported issue_type value")
    return normalized


def _resolve_current_assignee_id(*, actor: User, assignees: list[dict[str, object]]) -> int | None:
    actor_email = _string_or_none(getattr(actor, "email", ""))
    candidate_username = actor_email.split("@", 1)[0].lower() if actor_email else None
    if not candidate_username:
        return None
    for assignee in assignees:
        username = _string_or_none(assignee.get("username"))
        if username and username.lower() == candidate_username:
            return _int_or_none(assignee.get("id"))
    return None


def _issue_description_digest(issue_payload: dict) -> str:
    description = str(issue_payload.get("description") or "")
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def _issue_comment_count(issue_payload: dict) -> int | None:
    return _int_or_none(issue_payload.get("user_notes_count"))


def _parse_issue_url(url: str) -> tuple[str, str]:
    raw = url.strip()
    if not raw:
        raise ValidationError("Target issue URL is required")

    parsed = urlparse(raw)
    if not parsed.scheme:
        parsed = urlparse(f"{settings.gitlab_base_url.rstrip('/')}/{raw.lstrip('/')}")
    if not parsed.path:
        raise ValidationError("Target issue URL is invalid")

    base_host = urlparse(settings.gitlab_base_url).netloc.lower()
    if parsed.netloc and parsed.netloc.lower() != base_host:
        raise ValidationError("Target issue URL must point to configured GitLab host")

    match = ISSUE_URL_PATH_RE.match(parsed.path)
    if not match:
        raise ValidationError("Target issue URL must look like /group/project/-/issues/<iid>")
    return match.group("project_path"), match.group("issue_iid")


def _parse_gitlab_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
