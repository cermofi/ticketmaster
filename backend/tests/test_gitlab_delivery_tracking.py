from __future__ import annotations

from datetime import datetime
from datetime import timezone
from types import SimpleNamespace

import pytest

from ticketmaster.services.errors import ValidationError
from ticketmaster.services.gitlab_delivery_tracking import (
    GitLabApiError,
    TargetResolution,
    _expected_sync_status,
    _tracked_issue_invariant_errors,
    _parse_issue_url,
    _resolve_target_issue,
    _sort_tracked_issue_rows,
    normalize_sort,
    parse_updated_since,
)


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
