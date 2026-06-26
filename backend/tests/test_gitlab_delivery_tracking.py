from __future__ import annotations

from datetime import datetime
from datetime import timezone
from types import SimpleNamespace

import pytest

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
    normalize_sort,
    parse_updated_since,
)
from ticketmaster.models import GitLabTrackedIssue


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
