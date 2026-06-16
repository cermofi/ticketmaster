from __future__ import annotations

from fastapi.testclient import TestClient

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.services import tickets
from ticketmaster.services.ticket_activity import ticket_activity


def create_partner_ticket(db, data):
    ticket = tickets.create_partner_ticket(
        db,
        actor=data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Question for support",
        description="Need help",
        client_id=data["client_a"].id,
        participant_ids=[],
        source="test",
    )
    db.commit()
    return ticket


def test_ticket_activity_uses_audit_actor_not_assignee(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(
        db,
        ticket=ticket,
        actor=fixture_data["dm"],
        team="L2",
        assignee_ref=fixture_data["l2"].email,
        source="test",
    )
    tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["admin"], priority="High", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l2"], new_status="In progress", source="test")
    db.commit()

    activity = ticket_activity(db, ticket=ticket, viewer=fixture_data["dm"], limit=10)
    by_action = {row["action"]: row for row in activity}

    assert by_action["ticket.assign"]["author"] == "DM"
    assert by_action["ticket.assign"]["title"] == "Assigned to L2 · L2"
    assert by_action["ticket.priority_change"]["author"] == "Admin"
    assert by_action["ticket.status_change"]["author"] == "L2"
    assert by_action["ticket.create"]["author"] == "Responsible A"


def test_ticket_activity_hides_internal_notes_from_partners(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.add_internal_note(db, ticket=ticket, actor=fixture_data["dm"], body="Internal only", source="test")
    tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="Partner comment", source="test")
    db.commit()

    partner_activity = ticket_activity(db, ticket=ticket, viewer=fixture_data["responsible_a"], limit=20)
    internal_activity = ticket_activity(db, ticket=ticket, viewer=fixture_data["dm"], limit=20)

    partner_actions = {row["action"] for row in partner_activity}
    internal_actions = {row["action"] for row in internal_activity}

    assert "internal_note.create" not in partner_actions
    assert "comment.create" in partner_actions
    assert "internal_note.create" in internal_actions


def test_ticket_activity_endpoint_returns_history(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["dm"], ticket_type="Integration", source="test")
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: fixture_data["dm"]
    try:
        detail = TestClient(app).get(f"/api/tickets/{ticket.id}")
        history = TestClient(app).get(f"/api/tickets/{ticket.id}/activity")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert len(detail.json()["recent_activity"]) <= 3
    assert detail.json()["recent_activity"][0]["action"] == "ticket.type_change"
    assert detail.json()["recent_activity"][0]["author"] == "DM"

    assert history.status_code == 200
    assert any(row["action"] == "ticket.type_change" for row in history.json())
    assert all("author" in row and "title" in row for row in history.json())
