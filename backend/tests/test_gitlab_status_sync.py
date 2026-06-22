from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ticketmaster.api.main import app
from ticketmaster.core.config import settings
from ticketmaster.core.database import get_db
from ticketmaster.models import AuditLog, GitLabLink, GitLabSyncEvent, Ticket
from ticketmaster.models.entities import new_id
from ticketmaster.services import gitlab, tickets


@pytest.fixture(autouse=True)
def gitlab_env(monkeypatch):
    monkeypatch.setenv("GITLAB_DRY_RUN", "true")
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "test-webhook-secret")


def create_partner_ticket(db, data):
    return tickets.create_partner_ticket(
        db,
        actor=data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Partner ticket",
        description="Description",
        source="test",
    )


def _main_link(db, ticket_id: str) -> GitLabLink | None:
    return db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket_id, GitLabLink.is_main.is_(True)))


def _issue_payload(*, project_id: str, issue_iid: str, state: str = "opened", labels: list | None = None) -> dict:
    return {
        "object_kind": "issue",
        "project": {"id": int(project_id) if project_id.isdigit() else project_id},
        "object_attributes": {
            "iid": int(issue_iid) if issue_iid.isdigit() else issue_iid,
            "state": state,
            "labels": labels or [],
        },
    }


def _webhook_client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_validate_webhook_token():
    with patch("ticketmaster.services.gitlab.settings", replace(settings, gitlab_webhook_secret="secret")):
        assert gitlab.validate_webhook_token("secret") is True
        assert gitlab.validate_webhook_token("wrong") is False
        assert gitlab.validate_webhook_token(None) is False


def test_webhook_rejects_invalid_token(db, fixture_data):
    with patch("ticketmaster.api.routes.settings", replace(settings, gitlab_webhook_secret="test-webhook-secret")):
        client = _webhook_client(db)
        try:
            response = client.post("/api/gitlab/webhook", json=_issue_payload(project_id="503", issue_iid="1"), headers={"X-Gitlab-Token": "bad"})
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 401


def test_webhook_accepts_valid_token_for_unknown_link(db, fixture_data):
    patched = replace(settings, gitlab_webhook_secret="test-webhook-secret")
    with patch("ticketmaster.core.config.settings", patched), patch("ticketmaster.api.routes.settings", patched), patch("ticketmaster.services.gitlab.settings", patched):
        client = _webhook_client(db)
        try:
            response = client.post(
                "/api/gitlab/webhook",
                json=_issue_payload(project_id="503", issue_iid="999"),
                headers={"X-Gitlab-Token": "test-webhook-secret"},
            )
        finally:
            app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["reason"] == "link_not_found"


def test_webhook_rejects_when_secret_not_configured(db, fixture_data, monkeypatch):
    monkeypatch.delenv("GITLAB_WEBHOOK_SECRET", raising=False)
    client = _webhook_client(db)
    try:
        response = client.post("/api/gitlab/webhook", json=_issue_payload(project_id="503", issue_iid="1"), headers={"X-Gitlab-Token": "anything"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503


def test_inbound_mapping_applies_to_l3_ticket(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", source="test")
    link = _main_link(db, ticket.id)
    assert link is not None
    assert ticket.status == "Queued"

    payload = _issue_payload(project_id=link.project_id, issue_iid=link.issue_iid, labels=["In Progress"])
    payload["object_attributes"]["labels"] = [{"title": "In Progress"}]

    result = gitlab.apply_inbound_webhook(db, payload=payload)
    assert result["action"] == "conflict"
    assert ticket.status == "Queued"

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", assignee_ref=fixture_data["l3"].email, source="test")
    result = gitlab.apply_inbound_webhook(db, payload=payload)

    assert result["action"] == "updated"
    assert ticket.status == "In progress"
    assert link.status == "In Progress"


def test_inbound_conflict_skips_and_logs(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", assignee_ref=fixture_data["l3"].email, source="test")
    assert ticket.status == "Assigned"
    link = _main_link(db, ticket.id)
    assert link is not None

    payload = _issue_payload(project_id=link.project_id, issue_iid=link.issue_iid, labels=["To Do"])
    result = gitlab.apply_inbound_webhook(db, payload=payload)

    assert result["action"] == "conflict"
    assert ticket.status == "Assigned"
    event = db.scalar(select(GitLabSyncEvent).where(GitLabSyncEvent.ticket_id == ticket.id, GitLabSyncEvent.action == "webhook_inbound"))
    assert event is not None
    assert event.status == "warning"
    audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == ticket.id, AuditLog.action == "gitlab.webhook_inbound.conflict"))
    assert audit is not None


@pytest.mark.parametrize(
    ("gitlab_labels", "state", "expected_ticket_status"),
    [
        (["To Do"], "opened", "Queued"),
        ([], "opened", "Queued"),
        (["Done"], "opened", "Resolved"),
        ([], "closed", "Closed"),
    ],
)
def test_inbound_status_mapping(db, fixture_data, gitlab_labels, state, expected_ticket_status):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", assignee_ref=fixture_data["l3"].email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")
    link = _main_link(db, ticket.id)

    payload = _issue_payload(project_id=link.project_id, issue_iid=link.issue_iid, state=state, labels=[{"title": label} for label in gitlab_labels])
    result = gitlab.apply_inbound_webhook(db, payload=payload)

    if expected_ticket_status == "Queued":
        assert result["action"] == "conflict"
        assert ticket.status == "In progress"
    elif expected_ticket_status == "Resolved":
        assert result["action"] == "updated"
        assert ticket.status == "Resolved"
    elif expected_ticket_status == "Closed":
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="Resolved", source="test")
        result = gitlab.apply_inbound_webhook(db, payload=payload)
        assert result["action"] == "updated"
        assert ticket.status == "Closed"


def test_inbound_ignored_for_non_l3_ticket(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    link = GitLabLink(
        id=new_id(),
        ticket_id=ticket.id,
        project_id="503",
        issue_iid="99",
        web_url="https://gitlab.example/issues/99",
        issue_state="opened",
        status="Open",
    )
    db.add(link)
    db.flush()

    payload = _issue_payload(project_id="503", issue_iid="99", labels=["Done"])
    result = gitlab.apply_inbound_webhook(db, payload=payload)

    assert result["reason"] == "not_l3_ticket"
    assert ticket.status == "Queued"


@pytest.mark.parametrize(
    ("ticket_status", "expected_gitlab_status"),
    [
        ("Queued", "To Do"),
        ("Assigned", "To Do"),
        ("Need more info", "To Do"),
        ("In progress", "In Progress"),
        ("Resolved", "Done"),
        ("Closed", "Closed"),
    ],
)
def test_outbound_updates_link_for_key_statuses(db, fixture_data, ticket_status, expected_gitlab_status):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", assignee_ref=fixture_data["l3"].email, source="test")
    link = _main_link(db, ticket.id)

    if ticket_status == "In progress":
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")
    elif ticket_status == "Need more info":
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="Need more info", source="test")
    elif ticket_status == "Resolved":
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="Resolved", source="test")
    elif ticket_status == "Closed":
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="Resolved", source="test")
        tickets.close_ticket(db, ticket=ticket, actor=fixture_data["dm"], source="test")
    elif ticket_status == "Queued":
        tickets.unassign_ticket(db, ticket=ticket, actor=fixture_data["dm"], source="test")

    assert link.status == expected_gitlab_status


def test_outbound_skipped_without_l3_link(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    gitlab.push_ticket_status(db, ticket=ticket, source="test")
    assert _main_link(db, ticket.id) is None


def test_outbound_failure_does_not_change_ticket_status(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", assignee_ref=fixture_data["l3"].email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")
    assert ticket.status == "In progress"

    patched = replace(settings, gitlab_dry_run=False, gitlab_token="test-token")
    with patch("ticketmaster.services.gitlab.settings", patched), patch("ticketmaster.services.gitlab._push_issue_status", side_effect=RuntimeError("network down")):
        gitlab.push_ticket_status(db, ticket=ticket, source="test")

    assert ticket.status == "In progress"
    event = db.scalar(select(GitLabSyncEvent).where(GitLabSyncEvent.ticket_id == ticket.id, GitLabSyncEvent.action == "push_status", GitLabSyncEvent.status == "failed"))
    assert event is not None


def test_gitlab_status_mapping_functions():
    assert gitlab.gitlab_status_to_ticket_status("To Do") == "Queued"
    assert gitlab.gitlab_status_to_ticket_status("In Progress") == "In progress"
    assert gitlab.gitlab_status_to_ticket_status("Done") == "Resolved"
    assert gitlab.gitlab_status_to_ticket_status("Closed") == "Closed"
    assert gitlab.ticket_status_to_gitlab("Assigned") == ("opened", "To Do")
    assert gitlab.ticket_status_to_gitlab("Closed") == ("closed", None)
