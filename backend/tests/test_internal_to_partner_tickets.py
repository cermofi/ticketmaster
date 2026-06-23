from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.models import TicketParticipant
from ticketmaster.services import tickets


@contextmanager
def api_client(db, user=None):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    if user is not None:
        app.dependency_overrides[current_user] = lambda: user
    else:
        app.dependency_overrides.pop(current_user, None)
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_internal_user_can_create_ticket_to_partner_via_api(db, fixture_data):
    payload = {
        "partner_id": fixture_data["partner_a"].id,
        "owner_id": fixture_data["responsible_a"].id,
        "type": "Question",
        "priority": "Normal",
        "title": "API ticket to partner",
        "description": "Created by L1 through API",
        "client_id": fixture_data["client_a"].id,
        "participant_ids": [],
    }
    with api_client(db, fixture_data["l1"]) as client:
        response = client.post("/api/tickets/on-behalf", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["partner_id"] == fixture_data["partner_a"].id
    assert body["created_by_id"] == fixture_data["l1"].id


def test_partner_cannot_create_ticket_to_partner_via_api(db, fixture_data):
    payload = {
        "partner_id": fixture_data["partner_a"].id,
        "owner_id": fixture_data["responsible_a"].id,
        "type": "Question",
        "priority": "Normal",
        "title": "Blocked",
        "description": "Partner actor",
    }
    with api_client(db, fixture_data["responsible_a"]) as client:
        response = client.post("/api/tickets/on-behalf", json=payload)

    assert response.status_code == 403


def test_internal_user_can_list_partners_for_ticket_creation(db, fixture_data):
    with api_client(db, fixture_data["l1"]) as client:
        response = client.get("/api/partners")

    assert response.status_code == 200
    partner_ids = {row["id"] for row in response.json()}
    assert fixture_data["partner_a"].id in partner_ids


def test_internal_resolver_cannot_list_internal_users(db, fixture_data):
    with api_client(db, fixture_data["l1"]) as client:
        response = client.get("/api/users")

    assert response.status_code == 200
    kinds = {row["kind"] for row in response.json()}
    assert kinds == {"partner"}


def test_on_behalf_ticket_allows_owner_duplicated_in_participant_ids(db, fixture_data):
    ticket = tickets.create_partner_ticket_on_behalf(
        db,
        actor=fixture_data["l1"],
        partner_id=fixture_data["partner_a"].id,
        owner_ref=fixture_data["responsible_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="Owner also listed as participant",
        description="Should not duplicate participant rows",
        client_id=fixture_data["client_a"].id,
        participant_ids=[fixture_data["responsible_a"].id, fixture_data["technical_a"].id],
        source="test",
    )
    db.commit()

    participant_count = db.scalar(
        select(func.count())
        .select_from(TicketParticipant)
        .where(
            TicketParticipant.ticket_id == ticket.id,
            TicketParticipant.user_id == fixture_data["responsible_a"].id,
        )
    )
    assert participant_count == 1
    assert ticket.owner_id == fixture_data["responsible_a"].id


def test_on_behalf_api_accepts_owner_duplicated_in_participant_ids(db, fixture_data):
    payload = {
        "partner_id": fixture_data["partner_a"].id,
        "owner_id": fixture_data["responsible_a"].id,
        "type": "Question",
        "priority": "Normal",
        "title": "API duplicate participant guard",
        "description": "Owner repeated in participant_ids",
        "client_id": fixture_data["client_a"].id,
        "participant_ids": [fixture_data["responsible_a"].id],
    }
    with api_client(db, fixture_data["l1"]) as client:
        response = client.post("/api/tickets/on-behalf", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["owner_id"] == fixture_data["responsible_a"].id
