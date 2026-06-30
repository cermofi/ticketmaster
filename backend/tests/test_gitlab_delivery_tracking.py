from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ticketmaster.core.config import settings
from ticketmaster.services.errors import ValidationError
from ticketmaster.services.gitlab_delivery_tracking import (
    GitLabApiError,
    TargetResolution,
    _build_delivery_alert_payload,
    _emit_delivery_alert_if_needed,
    _expected_sync_status,
    _tracked_issue_invariant_errors,
    _tracked_issue_alert_changes,
    _row_matches_assignee_filter,
    _row_matches_label_filter,
    _parse_issue_url,
    _resolve_target_issue,
    _sort_tracked_issue_rows,
    close_tracked_issue,
    create_delivery_issue,
    edit_tracked_issue,
    get_delivery_issue_create_meta,
    get_tracked_issue_detail,
    move_tracked_issue,
    normalize_sort,
    parse_updated_since,
)
from ticketmaster.models import GitLabTrackedIssue


class DummyGitLabResponse:
    def __init__(self, *, status_code: int, payload: object, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):  # noqa: ANN201
        return self._payload


def test_parse_updated_since_accepts_date_only() -> None:
    value = parse_updated_since("2026-06-20")
    assert value is not None
    assert value.tzinfo == timezone.utc
    assert value.year == 2026
    assert value.month == 6
    assert value.day == 20


def test_parse_updated_since_accepts_iso_datetime() -> None:
    value = parse_updated_since("2026-06-20T10:30:00Z")
    assert value is not None
    assert value.tzinfo is not None
    assert value.hour == 10
    assert value.minute == 30


def test_parse_updated_since_rejects_invalid_value() -> None:
    with pytest.raises(ValidationError):
        parse_updated_since("20/06/2026")


def test_create_delivery_issue_calls_gitlab_with_normalized_payload() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    response = DummyGitLabResponse(
        status_code=201,
        payload={
            "id": 9001,
            "iid": 44,
            "project_id": 503,
            "title": "Create onboarding plan",
            "description": "Detailed checklist",
            "state": "opened",
            "labels": ["Delivery", "Customer"],
            "web_url": "https://gitlab.example.com/group/proj/-/issues/44",
            "created_at": "2026-06-29T10:00:00Z",
        },
    )
    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.httpx.post", return_value=response) as post_mock,
    ):
        created = create_delivery_issue(
            actor=actor,
            title="  Create onboarding plan  ",
            description="  Detailed checklist  ",
            labels=["Delivery", "delivery", "Customer", " "],
        )

    assert created["iid"] == "44"
    assert created["web_url"] == "https://gitlab.example.com/group/proj/-/issues/44"
    assert created["labels"] == ["Delivery", "Customer"]
    _, kwargs = post_mock.call_args
    assert kwargs["json"] == {
        "title": "Create onboarding plan",
        "description": "Detailed checklist",
        "labels": "Delivery,Customer",
    }


def test_create_delivery_issue_maps_gitlab_api_errors() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    response = DummyGitLabResponse(status_code=403, payload={"message": "forbidden"})

    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.httpx.post", return_value=response),
    ):
        with pytest.raises(ValidationError, match="GitLab API access forbidden"):
            create_delivery_issue(actor=actor, title="Blocked issue")


def test_create_delivery_issue_sends_extended_gitlab_fields() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    response = DummyGitLabResponse(
        status_code=201,
        payload={
            "id": 9002,
            "iid": 45,
            "project_id": 503,
            "title": "Incident in production",
            "description": "Incident body",
            "state": "opened",
            "labels": ["delivery", "incident", "custom"],
            "web_url": "https://gitlab.example.com/group/proj/-/issues/45",
            "created_at": "2026-06-29T10:05:00Z",
        },
    )
    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.httpx.post", return_value=response) as post_mock,
    ):
        create_delivery_issue(
            actor=actor,
            title="Incident in production",
            description="Incident body",
            labels=["custom"],
            assignee_ids=[77],
            milestone_id=12,
            due_date="2026-06-30",
            confidential=True,
            issue_type="incident",
        )

    _, kwargs = post_mock.call_args
    sent = kwargs["json"]
    assert sent["title"] == "Incident in production"
    assert sent["description"] == "Incident body"
    assert sent["labels"] == "custom"
    assert sent["assignee_ids"] == [77]
    assert sent["milestone_id"] == 12
    assert sent["due_date"] == "2026-06-30"
    assert sent["confidential"] is True
    assert sent["issue_type"] == "incident"


def test_get_delivery_issue_create_meta_collects_live_fields() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="team/delivery",
    )
    actor = SimpleNamespace(kind="internal", email="jane.doe@example.com")

    class DummyClient:
        def __init__(self, **kwargs):  # noqa: ANN003, ANN204
            pass

        def close(self) -> None:
            return None

        def get_project(self, project_id_or_path: str) -> dict:
            assert project_id_or_path == "team/delivery"
            return {
                "id": 503,
                "name": "Delivery",
                "path_with_namespace": "team/delivery",
                "web_url": "https://gitlab.example.com/team/delivery",
            }

        def list_project_labels(self, project_id_or_path: str) -> list[dict]:
            assert project_id_or_path == "503"
            return [
                {"id": 1, "name": "delivery", "description": "Delivery label", "color": "#00ff00"},
                {"id": 2, "name": "customer", "description": "", "color": "#0000ff"},
            ]

        def list_project_milestones(self, project_id_or_path: str) -> list[dict]:
            assert project_id_or_path == "503"
            return [{"id": 12, "title": "Sprint 27", "description": "", "due_date": "2026-07-05", "web_url": "https://gitlab.example.com/-/milestones/12"}]

        def list_project_members(self, project_id_or_path: str) -> list[dict]:
            assert project_id_or_path == "503"
            return [
                {"id": 77, "username": "jane.doe", "name": "Jane Doe", "avatar_url": None, "web_url": "https://gitlab.example.com/jane.doe", "state": "active"},
                {"id": 99, "username": "john", "name": "John", "avatar_url": None, "web_url": "https://gitlab.example.com/john", "state": "active"},
            ]

    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.GitLabReadOnlyClient", DummyClient),
    ):
        meta = get_delivery_issue_create_meta(actor=actor)

    assert meta["project"]["path_with_namespace"] == "team/delivery"
    assert [label["title"] for label in meta["labels"]] == ["customer", "delivery"]
    assert meta["milestones"][0]["title"] == "Sprint 27"
    assert len(meta["assignees"]) == 2
    assert meta["current_assignee_id"] == 77


def test_get_tracked_issue_detail_collects_issue_and_notes() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    tracked = GitLabTrackedIssue(
        id="tracked-1",
        delivery_project_id="503",
        delivery_issue_iid="11",
        delivery_title="Delivery issue title",
        delivery_url="https://gitlab.example.com/team/delivery/-/issues/11",
        delivery_state="opened",
        target_project_id="777",
        target_issue_iid="42",
        sync_status="ok",
    )

    class DummySession:
        @staticmethod
        def get(model, tracked_issue_id: str):  # noqa: ANN205, ANN001
            assert model is GitLabTrackedIssue
            if tracked_issue_id == tracked.id:
                return tracked
            return None

    class DummyClient:
        def __init__(self, **kwargs):  # noqa: ANN003, ANN204
            pass

        def close(self) -> None:
            return None

        @staticmethod
        def get_project_issue(project_id: str, issue_iid: str) -> dict:
            assert project_id == "777"
            assert issue_iid == "42"
            return {
                "id": 4002,
                "iid": 42,
                "project_id": 777,
                "title": "Target issue title",
                "description": "## Body",
                "state": "opened",
                "labels": ["delivery", "backend"],
                "issue_type": "task",
                "confidential": False,
                "assignees": [{"id": 77, "name": "Jane Doe", "username": "jane"}],
                "author": {"id": 1, "name": "Author", "username": "author"},
                "due_date": "2026-07-01",
                "created_at": "2026-06-20T08:00:00Z",
                "updated_at": "2026-06-21T09:00:00Z",
                "web_url": "https://gitlab.example.com/team/target/-/issues/42",
                "user_notes_count": 1,
                "references": {"full": "team/target#42"},
            }

        @staticmethod
        def get_issue_notes(project_id: str, issue_iid: str, *, sort: str = "desc", order_by: str = "updated_at") -> list[dict]:
            assert project_id == "777"
            assert issue_iid == "42"
            assert sort == "asc"
            assert order_by == "created_at"
            return [
                {
                    "id": 9001,
                    "body": "First note",
                    "system": False,
                    "internal": False,
                    "created_at": "2026-06-20T10:00:00Z",
                    "updated_at": "2026-06-20T10:00:00Z",
                    "author": {"id": 2, "name": "Reviewer", "username": "reviewer"},
                }
            ]

    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.GitLabReadOnlyClient", DummyClient),
    ):
        detail = get_tracked_issue_detail(DummySession(), actor=actor, tracked_issue_id="tracked-1")

    assert detail["source_issue"] == "target"
    assert detail["issue"]["title"] == "Target issue title"
    assert detail["issue"]["reference"] == "team/target#42"
    assert detail["issue"]["assignees"][0]["name"] == "Jane Doe"
    assert detail["notes"][0]["body"] == "First note"
    assert detail["tracked_issue"]["delivery_issue_iid"] == "11"


def test_close_tracked_issue_closes_target_issue() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    tracked = GitLabTrackedIssue(
        id="tracked-1",
        delivery_project_id="503",
        delivery_issue_iid="11",
        delivery_title="Delivery issue title",
        delivery_url="https://gitlab.example.com/team/delivery/-/issues/11",
        delivery_state="opened",
        target_project_id="777",
        target_issue_iid="42",
        sync_status="ok",
    )

    class DummySession:
        @staticmethod
        def get(model, tracked_issue_id: str):  # noqa: ANN205, ANN001
            assert model is GitLabTrackedIssue
            if tracked_issue_id == tracked.id:
                return tracked
            return None

    response = DummyGitLabResponse(
        status_code=200,
        payload={
            "id": 4002,
            "iid": 42,
            "project_id": 777,
            "title": "Target issue title",
            "description": "Body",
            "state": "closed",
            "labels": ["delivery"],
        },
    )
    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.httpx.request", return_value=response) as request_mock,
    ):
        issue = close_tracked_issue(DummySession(), actor=actor, tracked_issue_id="tracked-1")

    _, kwargs = request_mock.call_args
    assert kwargs["method"] == "PUT"
    assert "/projects/777/issues/42" in kwargs["url"]
    assert kwargs["json"] == {"state_event": "close"}
    assert issue["state"] == "closed"


def test_edit_tracked_issue_updates_title_and_description() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    tracked = GitLabTrackedIssue(
        id="tracked-1",
        delivery_project_id="503",
        delivery_issue_iid="11",
        delivery_title="Delivery issue title",
        delivery_url="https://gitlab.example.com/team/delivery/-/issues/11",
        delivery_state="opened",
        target_project_id="777",
        target_issue_iid="42",
        sync_status="ok",
    )

    class DummySession:
        @staticmethod
        def get(model, tracked_issue_id: str):  # noqa: ANN205, ANN001
            assert model is GitLabTrackedIssue
            if tracked_issue_id == tracked.id:
                return tracked
            return None

    response = DummyGitLabResponse(
        status_code=200,
        payload={
            "id": 4002,
            "iid": 42,
            "project_id": 777,
            "title": "Updated issue title",
            "description": "Updated markdown body",
            "state": "opened",
            "labels": ["delivery"],
        },
    )
    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.httpx.request", return_value=response) as request_mock,
    ):
        issue = edit_tracked_issue(
            DummySession(),
            actor=actor,
            tracked_issue_id="tracked-1",
            title="  Updated issue title  ",
            description="Updated markdown body",
        )

    _, kwargs = request_mock.call_args
    assert kwargs["method"] == "PUT"
    assert "/projects/777/issues/42" in kwargs["url"]
    assert kwargs["json"] == {"title": "Updated issue title", "description": "Updated markdown body"}
    assert issue["title"] == "Updated issue title"


def test_move_tracked_issue_calls_gitlab_move_endpoint() -> None:
    patched = replace(
        settings,
        gitlab_base_url="https://gitlab.example.com",
        gitlab_token="secret-token",
        gitlab_delivery_project_id="503",
    )
    actor = SimpleNamespace(kind="internal")
    tracked = GitLabTrackedIssue(
        id="tracked-1",
        delivery_project_id="503",
        delivery_issue_iid="11",
        delivery_title="Delivery issue title",
        delivery_url="https://gitlab.example.com/team/delivery/-/issues/11",
        delivery_state="opened",
        target_project_id="777",
        target_issue_iid="42",
        sync_status="ok",
    )

    class DummySession:
        @staticmethod
        def get(model, tracked_issue_id: str):  # noqa: ANN205, ANN001
            assert model is GitLabTrackedIssue
            if tracked_issue_id == tracked.id:
                return tracked
            return None

    response = DummyGitLabResponse(
        status_code=200,
        payload={
            "id": 5001,
            "iid": 75,
            "project_id": 888,
            "title": "Moved issue",
            "description": "Body",
            "state": "opened",
            "labels": ["delivery"],
        },
    )
    with (
        patch("ticketmaster.services.gitlab_delivery_tracking.settings", patched),
        patch("ticketmaster.services.gitlab_delivery_tracking.httpx.request", return_value=response) as request_mock,
    ):
        issue = move_tracked_issue(
            DummySession(),
            actor=actor,
            tracked_issue_id="tracked-1",
            to_project_id="team/new-target",
        )

    _, kwargs = request_mock.call_args
    assert kwargs["method"] == "POST"
    assert kwargs["url"].endswith("/projects/777/issues/42/move")
    assert kwargs["json"] == {"to_project_id": "team/new-target"}
    assert issue["project_id"] == "888"


def test_parse_issue_url_accepts_absolute_gitlab_url() -> None:
    project_path, issue_iid = _parse_issue_url("https://gitlab.teskalabs.int/group-a/project-x/-/issues/123")
    assert project_path == "group-a/project-x"
    assert issue_iid == "123"


def test_parse_issue_url_accepts_relative_path() -> None:
    project_path, issue_iid = _parse_issue_url("/group-a/project-x/-/issues/777")
    assert project_path == "group-a/project-x"
    assert issue_iid == "777"


def test_parse_issue_url_rejects_different_host() -> None:
    with pytest.raises(ValidationError):
        _parse_issue_url("https://example.com/group-a/project-x/-/issues/123")


def test_normalize_sort_fallbacks_to_defaults() -> None:
    sort_by, sort_direction = normalize_sort("unsupported-field", "sideways")
    assert sort_by == "last_gitlab_update"
    assert sort_direction == "desc"


def test_sort_rows_by_assignee_desc() -> None:
    base = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            delivery_issue_iid="1",
            delivery_title="A",
            target_state="opened",
            target_team_name="team-a",
            target_url="http://example/1",
            target_assignees=[{"name": "Alice"}],
            target_labels=["x"],
            sync_status="ok",
            target_updated_at=base,
            delivery_updated_at=base,
            delivery_url="http://delivery/1",
            resolution_source="system_note",
        ),
        SimpleNamespace(
            delivery_issue_iid="2",
            delivery_title="B",
            target_state="opened",
            target_team_name="team-a",
            target_url="http://example/2",
            target_assignees=[{"name": "Bob"}],
            target_labels=["y"],
            sync_status="ok",
            target_updated_at=base,
            delivery_updated_at=base,
            delivery_url="http://delivery/2",
            resolution_source="system_note",
        ),
    ]
    sorted_rows = _sort_tracked_issue_rows(rows, sort_by="assignee", sort_direction="desc")
    assert [row.delivery_issue_iid for row in sorted_rows] == ["2", "1"]


def test_sort_rows_by_ticket_id_asc() -> None:
    rows = [
        SimpleNamespace(delivery_issue_iid="20", delivery_title="A"),
        SimpleNamespace(delivery_issue_iid="3", delivery_title="B"),
        SimpleNamespace(delivery_issue_iid="11", delivery_title="C"),
    ]
    sorted_rows = _sort_tracked_issue_rows(rows, sort_by="ticket_id", sort_direction="asc")
    assert [row.delivery_issue_iid for row in sorted_rows] == ["3", "11", "20"]


def test_row_matches_assignee_filter_uses_name_and_username() -> None:
    row = SimpleNamespace(
        target_assignees=[
            {"name": "Alice Delivery", "username": "adelivery"},
            {"name": None, "username": "bworker"},
        ],
    )
    assert _row_matches_assignee_filter(row, "alice")
    assert _row_matches_assignee_filter(row, "bworker")
    assert not _row_matches_assignee_filter(row, "charlie")


def test_sort_rows_by_team_id_uses_target_issue_iid() -> None:
    rows = [
        SimpleNamespace(delivery_issue_iid="1", delivery_title="A", target_issue_iid="200", target_url="http://example/200"),
        SimpleNamespace(delivery_issue_iid="2", delivery_title="B", target_issue_iid="15", target_url="http://example/15"),
    ]
    sorted_rows = _sort_tracked_issue_rows(rows, sort_by="target_issue_url", sort_direction="asc")
    assert [row.delivery_issue_iid for row in sorted_rows] == ["2", "1"]


def test_row_matches_label_filter_prefers_target_labels_with_delivery_fallback() -> None:
    with_target = SimpleNamespace(target_labels=["Ops"], delivery_labels=["Delivery"])
    with_delivery_only = SimpleNamespace(target_labels=[], delivery_labels=["Delivery"])
    assert _row_matches_label_filter(with_target, "ops")
    assert not _row_matches_label_filter(with_target, "delivery")
    assert _row_matches_label_filter(with_delivery_only, "delivery")


def test_tracked_issue_alert_changes_detect_modified_values() -> None:
    previous = {"target_state": "opened", "sync_status": "ok", "last_gitlab_update": "2026-06-26T10:00:00+00:00"}
    current = {"target_state": "closed", "sync_status": "target_missing", "last_gitlab_update": "2026-06-26T10:05:00+00:00"}
    changes = _tracked_issue_alert_changes(previous, current)
    fields = {change["field"] for change in changes}
    assert "target_state" in fields
    assert "sync_status" in fields
    assert "last_gitlab_update" in fields


def test_build_delivery_alert_payload_for_new_issue() -> None:
    tracked = SimpleNamespace(sync_status="ok", target_issue_iid="101", target_state="opened", delivery_state="opened")
    payload = _build_delivery_alert_payload(tracked, previous_snapshot=None, current_snapshot={"sync_status": "ok"}, is_new=True)
    assert payload is not None
    assert payload["kind"] == "tracked"


def test_build_delivery_alert_payload_for_state_change() -> None:
    tracked = SimpleNamespace(sync_status="ok", target_issue_iid="55", target_state="closed", delivery_state="opened")
    payload = _build_delivery_alert_payload(
        tracked,
        previous_snapshot={"target_state": "opened"},
        current_snapshot={"target_state": "closed"},
        is_new=False,
    )
    assert payload is not None
    assert payload["kind"] == "state_changed"


def test_build_delivery_alert_payload_for_comment_addition() -> None:
    tracked = SimpleNamespace(sync_status="ok", target_issue_iid="55", target_state="opened", delivery_state="opened")
    payload = _build_delivery_alert_payload(
        tracked,
        previous_snapshot={
            "activity_source": "target",
            "activity_comment_count": 2,
            "activity_description_digest": "same",
        },
        current_snapshot={
            "activity_source": "target",
            "activity_comment_count": 3,
            "activity_description_digest": "same",
        },
        is_new=False,
    )
    assert payload is not None
    assert payload["kind"] == "comment_added"


def test_build_delivery_alert_payload_for_description_edit() -> None:
    tracked = SimpleNamespace(sync_status="ok", target_issue_iid="55", target_state="opened", delivery_state="opened")
    payload = _build_delivery_alert_payload(
        tracked,
        previous_snapshot={
            "activity_source": "target",
            "activity_comment_count": 2,
            "activity_description_digest": "old",
        },
        current_snapshot={
            "activity_source": "target",
            "activity_comment_count": 2,
            "activity_description_digest": "new",
        },
        is_new=False,
    )
    assert payload is not None
    assert payload["kind"] == "description_edited"


def test_build_delivery_alert_payload_for_assignee_change() -> None:
    tracked = SimpleNamespace(sync_status="ok", target_issue_iid="55", target_state="opened", delivery_state="opened")
    payload = _build_delivery_alert_payload(
        tracked,
        previous_snapshot={"target_assignees": ("Alice",)},
        current_snapshot={"target_assignees": ("Bob",)},
        is_new=False,
    )
    assert payload is not None
    assert payload["kind"] == "assignee_changed"


def test_build_delivery_alert_payload_skips_marker_bootstrap_noise() -> None:
    tracked = SimpleNamespace(sync_status="ok", target_issue_iid="55", target_state="opened", delivery_state="opened")
    payload = _build_delivery_alert_payload(
        tracked,
        previous_snapshot={
            "activity_source": "",
            "activity_comment_count": "",
            "activity_description_digest": "",
        },
        current_snapshot={
            "activity_source": "target",
            "activity_comment_count": 4,
            "activity_description_digest": "new-digest",
        },
        is_new=False,
    )
    assert payload is None


def test_emit_delivery_alert_flushes_pending_tracked_issue_before_insert() -> None:
    class DummySession:
        def __init__(self, tracked_issue: GitLabTrackedIssue) -> None:
            self.new = {tracked_issue}
            self.flush_calls: list[list[GitLabTrackedIssue] | None] = []
            self.added: list[object] = []

        def flush(self, objects=None) -> None:  # noqa: ANN001
            self.flush_calls.append(objects)

        def add(self, obj) -> None:  # noqa: ANN001
            self.added.append(obj)

    tracked = GitLabTrackedIssue(
        id="tracked-issue-1",
        delivery_project_id="503",
        delivery_issue_iid="15",
        delivery_title="ICZ - Upgrade Elasticsearch",
        delivery_url="http://gitlab.example/team/delivery/-/issues/15",
        delivery_state="opened",
        sync_status="ok",
    )
    session = DummySession(tracked)

    _emit_delivery_alert_if_needed(
        session,
        tracked=tracked,
        previous_snapshot=None,
        is_new=True,
    )

    assert session.flush_calls == [[tracked]]
    assert len(session.added) == 1
    alert = session.added[0]
    assert getattr(alert, "tracked_issue_id", None) == tracked.id


def test_resolve_target_issue_without_hints_stays_in_delivery() -> None:
    class DummyClient:
        @staticmethod
        def get_issue_notes(project_id: str, issue_iid: str) -> list[dict]:
            return []

    resolution = _resolve_target_issue(
        client=DummyClient(),
        delivery_payload={"project_id": "503", "iid": "10"},
        mapping=None,
        project_cache={},
    )
    assert resolution.issue is None
    assert resolution.has_target_hint is False


def test_resolve_target_issue_keeps_missing_when_hint_exists() -> None:
    class DummyClient:
        @staticmethod
        def get_global_issue(issue_id: str) -> dict:
            raise GitLabApiError("not found", status_code=404)

        @staticmethod
        def get_issue_notes(project_id: str, issue_iid: str) -> list[dict]:
            return []

    resolution = _resolve_target_issue(
        client=DummyClient(),
        delivery_payload={"project_id": "503", "iid": "10", "moved_to_id": "9999"},
        mapping=None,
        project_cache={},
    )
    assert resolution.issue is None
    assert resolution.has_target_hint is True


def test_expected_sync_status_resolution_matrix() -> None:
    assert _expected_sync_status(
        TargetResolution(
            issue={"id": 1},
            source="moved_to_id",
            used_manual_mapping=False,
            used_moved_to=True,
            used_note_fallback=False,
            has_target_hint=True,
            fatal_error=None,
        )
    ) == "ok"
    assert _expected_sync_status(
        TargetResolution(
            issue=None,
            source="none",
            used_manual_mapping=False,
            used_moved_to=False,
            used_note_fallback=False,
            has_target_hint=False,
            fatal_error=None,
        )
    ) == "in_delivery"
    assert _expected_sync_status(
        TargetResolution(
            issue=None,
            source="none",
            used_manual_mapping=False,
            used_moved_to=True,
            used_note_fallback=False,
            has_target_hint=True,
            fatal_error=None,
        )
    ) == "target_missing"
    assert _expected_sync_status(
        TargetResolution(
            issue=None,
            source="none",
            used_manual_mapping=False,
            used_moved_to=False,
            used_note_fallback=False,
            has_target_hint=True,
            fatal_error="boom",
        )
    ) == "error"


def test_tracked_issue_invariant_errors_flags_bad_states() -> None:
    row = SimpleNamespace(
        sync_status="in_delivery",
        target_missing=True,
        target_project_id="212",
        target_issue_iid="123",
        target_url="http://example",
        resolution_source="system_note",
    )
    errors = _tracked_issue_invariant_errors(row)
    assert len(errors) >= 3
