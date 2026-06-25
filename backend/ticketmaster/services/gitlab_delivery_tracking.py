from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cmp_to_key
from urllib.parse import quote_plus, urlparse

import httpx
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import GitLabIssueManualMapping, GitLabIssueSyncRun, GitLabTrackedIssue, User
from ticketmaster.models.entities import new_id
from ticketmaster.services.errors import NotFoundError, ValidationError

logger = logging.getLogger("ticketmaster.gitlab.delivery_tracking")
SYNC_ADVISORY_LOCK_ID = 90503

ISSUE_URL_PATH_RE = re.compile(r"^/(?P<project_path>.+)/-/issues/(?P<issue_iid>\d+)/?$")
ISSUE_URL_IN_TEXT_RE = re.compile(r"https?://[^\s)]+/-/issues/\d+", re.IGNORECASE)
MOVED_NOTE_RE = re.compile(r"moved to\s+(?P<project_path>[A-Za-z0-9_.\-/]+)#(?P<issue_iid>\d+)", re.IGNORECASE)
SORT_FIELDS = {
    "delivery_issue",
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

    def get_issue_notes(self, project_id: str, issue_iid: str) -> list[dict]:
        notes: list[dict] = []
        page = 1
        while True:
            response = self._request(
                f"/projects/{quote_plus(str(project_id))}/issues/{quote_plus(str(issue_iid))}/notes",
                params={"per_page": 100, "page": page, "sort": "desc", "order_by": "updated_at"},
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
    latest_run = db.scalar(select(GitLabIssueSyncRun).order_by(GitLabIssueSyncRun.started_at.desc()))
    return {
        "configured": _sync_configured(),
        "target_teams": configured_teams,
        "states": states,
        "sync_interval_seconds": settings.gitlab_sync_interval_seconds,
        "last_sync_run": serialize_sync_run(latest_run) if latest_run else None,
    }


def list_tracked_issues(
    db: Session,
    *,
    search: str | None = None,
    target_team: str | None = None,
    state: str | None = None,
    missing_mapping: bool | None = None,
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

    all_rows = db.scalars(stmt).all()
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

    if resolution.issue is not None:
        _apply_target_fields(
            tracked,
            target_issue=resolution.issue,
            source=resolution.source,
            target_teams=target_teams,
            client=client,
            project_cache=project_cache,
        )
        tracked.sync_status = "ok"
        tracked.sync_error = None
        tracked.target_missing = False
        return IssueSyncOutcome(
            status="ok",
            used_manual_mapping=resolution.used_manual_mapping,
            used_moved_to=resolution.used_moved_to,
            used_note_fallback=resolution.used_note_fallback,
        )

    _clear_target_fields(tracked)
    if resolution.fatal_error:
        tracked.sync_status = "error"
        tracked.sync_error = resolution.fatal_error
        tracked.target_missing = False
        tracked.resolution_source = "error"
        return IssueSyncOutcome(status="error")

    if not resolution.has_target_hint:
        tracked.sync_status = "in_delivery"
        tracked.sync_error = None
        tracked.target_missing = False
        tracked.resolution_source = "delivery"
        tracked.target_team_name = "Delivery"
        return IssueSyncOutcome(
            status="ok",
            used_manual_mapping=resolution.used_manual_mapping,
            used_moved_to=resolution.used_moved_to,
            used_note_fallback=resolution.used_note_fallback,
        )

    tracked.sync_status = "target_missing"
    tracked.sync_error = "Target issue could not be resolved automatically"
    tracked.target_missing = True
    tracked.resolution_source = "target_missing"
    return IssueSyncOutcome(
        status="target_missing",
        used_manual_mapping=resolution.used_manual_mapping,
        used_moved_to=resolution.used_moved_to,
        used_note_fallback=resolution.used_note_fallback,
    )


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
    if sort_by == "current_state":
        return (_string_or_none(row.target_state) or _string_or_none(row.delivery_state) or "").lower()
    if sort_by == "target_team":
        return (_string_or_none(row.target_team_name) or "").lower()
    if sort_by == "target_issue_url":
        return (_string_or_none(row.target_url) or "").lower()
    if sort_by == "assignee":
        return (_first_assignee_name(row) or "").lower()
    if sort_by == "labels":
        target_labels = _normalize_labels(row.target_labels)
        if target_labels:
            return ",".join(target_labels).lower()
        return ",".join(_normalize_labels(row.delivery_labels)).lower()
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
    assignees = _normalize_assignees(row.target_assignees)
    if not assignees:
        return None
    first = assignees[0]
    return _string_or_none(first.get("name")) or _string_or_none(first.get("username"))


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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
