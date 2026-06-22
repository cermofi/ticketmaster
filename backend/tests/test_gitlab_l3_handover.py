from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from ticketmaster.models import GitLabLink, Ticket
from ticketmaster.models.constants import TICKET_TYPES
from ticketmaster.services import tickets
from ticketmaster.services.errors import ValidationError


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


@pytest.fixture(autouse=True)
def gitlab_dry_run(monkeypatch):
    monkeypatch.setenv("GITLAB_DRY_RUN", "true")


def _main_link(db, ticket_id: str) -> GitLabLink | None:
    return db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket_id, GitLabLink.is_main.is_(True)))


def test_l3_assign_triggers_gitlab_issue_creation(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    assert ticket.resolver_team is None

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", source="test")

    assert ticket.resolver_team == "L3"
    link = _main_link(db, ticket.id)
    assert link is not None
    assert link.issue_iid.startswith("dry-")


def test_l3_assign_failure_blocks_handover(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    original_status = ticket.status

    with patch("ticketmaster.services.tickets.gitlab.create_main_issue", side_effect=ValidationError("GitLab issue creation failed: boom")):
        with pytest.raises(ValidationError, match="GitLab issue creation failed"):
            tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", source="test")

    assert ticket.resolver_team is None
    assert ticket.status == original_status
    assert _main_link(db, ticket.id) is None


@pytest.mark.parametrize("ticket_type", sorted(TICKET_TYPES))
def test_l3_assign_applies_to_all_ticket_types(db, fixture_data, ticket_type):
    ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type=ticket_type,
        priority="Normal",
        title=f"{ticket_type} ticket",
        description="Description",
        source="test",
    )

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", source="test")

    assert ticket.resolver_team == "L3"
    assert _main_link(db, ticket.id) is not None


def test_l3_create_internal_triggers_gitlab_issue(db, fixture_data):
    ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["dm"],
        ticket_type="Operational Request",
        priority="Normal",
        title="Internal L3",
        description="Internal",
        team="L3",
        source="test",
    )

    assert ticket.resolver_team == "L3"
    assert _main_link(db, ticket.id) is not None


def test_l3_create_internal_failure_blocks_ticket(db, fixture_data):
    with patch("ticketmaster.services.tickets.gitlab.create_main_issue", side_effect=ValidationError("GitLab issue creation failed: boom")):
        with pytest.raises(ValidationError, match="GitLab issue creation failed"):
            tickets.create_internal_ticket(
                db,
                actor=fixture_data["dm"],
                ticket_type="Operational Request",
                priority="Normal",
                title="Internal L3",
                description="Internal",
                team="L3",
                source="test",
            )

    db.rollback()
    assert db.scalar(select(Ticket).where(Ticket.title == "Internal L3")) is None


def test_l3_create_system_triggers_gitlab_issue(db, fixture_data):
    ticket = tickets.create_system_ticket(
        db,
        partner_id=fixture_data["partner_a"].id,
        ticket_type="Integration",
        priority="High",
        title="System L3",
        description="System",
        team="L3",
        source="test",
    )

    assert ticket.resolver_team == "L3"
    assert _main_link(db, ticket.id) is not None


def test_l3_create_system_failure_blocks_ticket(db, fixture_data):
    with patch("ticketmaster.services.tickets.gitlab.create_main_issue", side_effect=ValidationError("GitLab issue creation failed: boom")):
        with pytest.raises(ValidationError, match="GitLab issue creation failed"):
            tickets.create_system_ticket(
                db,
                partner_id=fixture_data["partner_a"].id,
                ticket_type="Integration",
                priority="High",
                title="System L3",
                description="System",
                team="L3",
                source="test",
            )

    db.rollback()
    assert db.scalar(select(Ticket).where(Ticket.title == "System L3")) is None


def test_ticket_detail_ui_has_no_manual_gitlab_actions():
    source = Path(__file__).resolve().parents[2] / "frontend" / "src" / "ticketmaster" / "screens" / "TicketDetailScreen.jsx"
    content = source.read_text()

    assert "gitlab/create-issue" not in content
    assert "gitlab/sync-status" not in content
    assert "Create GitLab issue" not in content
    assert "Sync GitLab" not in content
