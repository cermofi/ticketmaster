from __future__ import annotations

from datetime import timezone

import pytest

from ticketmaster.services.errors import ValidationError
from ticketmaster.services.gitlab_delivery_tracking import _parse_issue_url, parse_updated_since


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
