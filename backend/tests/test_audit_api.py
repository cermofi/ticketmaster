from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.services import audit as audit_service
from ticketmaster.services import tickets
from ticketmaster.services.audit_list import parse_audit_filter_datetime


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


def _seed_audit_rows(db, fixture_data):
    ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Audit filter ticket",
        description="Details",
        client_id=fixture_data["client_a"].id,
        participant_ids=[],
        source="test",
    )
    audit_service.audit(
        db,
        entity_type="Auth",
        entity_id="someone@example.test",
        action="auth.login_failed",
        source="ui",
        new_value={"method": "password"},
    )
    audit_service.audit(
        db,
        entity_type="Ticket",
        entity_id=ticket.id,
        action="ticket.note",
        actor=fixture_data["admin"],
        source="system",
        old_value=None,
        new_value=None,
    )
    db.commit()
    return ticket


def test_parse_audit_filter_datetime_accepts_iso_and_display_format():
    iso = parse_audit_filter_datetime("2026-06-02T13:11:07")
    display = parse_audit_filter_datetime("02.06.2026 13:11:07")
    assert iso == display
    assert iso.tzinfo == timezone.utc


def test_audit_list_requires_admin_or_dm(db, fixture_data):
    with api_client(db, fixture_data["l1"]) as client:
        response = client.get("/api/audit")
    assert response.status_code == 403


def test_audit_list_entity_id_filter_backwards_compatible(db, fixture_data):
    ticket = _seed_audit_rows(db, fixture_data)
    with api_client(db, fixture_data["admin"]) as client:
        response = client.get("/api/audit", params={"entity_id": ticket.id})
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert all(row["entity_id"] == ticket.id for row in payload)


def test_audit_list_action_and_source_filters(db, fixture_data):
    _seed_audit_rows(db, fixture_data)
    with api_client(db, fixture_data["dm"]) as client:
        action_response = client.get("/api/audit", params={"action": "auth.login"})
        source_response = client.get("/api/audit", params={"source": "ui"})
    assert action_response.status_code == 200
    assert all("auth.login" in row["action"] for row in action_response.json())
    assert source_response.status_code == 200
    assert all(row["source"] == "ui" for row in source_response.json())


def test_audit_list_entity_type_and_changed_by_filters(db, fixture_data):
    _seed_audit_rows(db, fixture_data)
    with api_client(db, fixture_data["admin"]) as client:
        type_response = client.get("/api/audit", params={"entity_type": "Auth"})
        changed_by_response = client.get("/api/audit", params={"changed_by": "Admin"})
    assert type_response.status_code == 200
    assert all(row["entity_type"] == "Auth" for row in type_response.json())
    assert changed_by_response.status_code == 200
    assert all("Admin" in row["changed_by_label"] for row in changed_by_response.json())


def test_audit_list_search_and_has_details_filters(db, fixture_data):
    _seed_audit_rows(db, fixture_data)
    with api_client(db, fixture_data["admin"]) as client:
        search_response = client.get("/api/audit", params={"search": "password"})
        details_response = client.get("/api/audit", params={"has_details": "true"})
        no_details_response = client.get("/api/audit", params={"action": "ticket.note"})
    assert search_response.status_code == 200
    assert any(row["action"] == "auth.login_failed" for row in search_response.json())
    assert details_response.status_code == 200
    assert all(row["old_value"] is not None or row["new_value"] is not None for row in details_response.json())
    assert no_details_response.status_code == 200
    assert all(row["old_value"] is None and row["new_value"] is None for row in no_details_response.json())


def test_audit_list_datetime_range_filter(db, fixture_data):
    _seed_audit_rows(db, fixture_data)
    now = datetime.now(timezone.utc)
    with api_client(db, fixture_data["admin"]) as client:
        in_range = client.get(
            "/api/audit",
            params={
                "from": (now - timedelta(hours=1)).isoformat(),
                "to": (now + timedelta(hours=1)).isoformat(),
            },
        )
        out_of_range = client.get(
            "/api/audit",
            params={
                "from": (now + timedelta(days=1)).isoformat(),
            },
        )
    assert in_range.status_code == 200
    assert len(in_range.json()) >= 2
    assert out_of_range.status_code == 200
    assert out_of_range.json() == []


def test_audit_list_combined_filters(db, fixture_data):
    _seed_audit_rows(db, fixture_data)
    with api_client(db, fixture_data["admin"]) as client:
        response = client.get(
            "/api/audit",
            params={
                "entity_type": "Auth",
                "source": "ui",
                "has_details": "true",
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["action"] == "auth.login_failed"


def test_audit_options_returns_distinct_values(db, fixture_data):
    _seed_audit_rows(db, fixture_data)
    with api_client(db, fixture_data["admin"]) as client:
        response = client.get("/api/audit/options")
    assert response.status_code == 200
    payload = response.json()
    assert "ticket.create" in payload["actions"]
    assert "ui" in payload["sources"]
    assert "Auth" in payload["entity_types"]
