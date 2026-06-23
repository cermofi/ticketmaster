from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.core.security import decode_token
from ticketmaster.models import AuditLog
from ticketmaster.services.errors import PermissionDenied
from ticketmaster.services import auth


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


def test_sign_in_as_partner_success_for_admin_and_dm(db, fixture_data):
    for actor_key in ("admin", "dm"):
        actor = fixture_data[actor_key]
        target = fixture_data["responsible_a"]
        with api_client(db, actor) as client:
            response = client.post("/api/auth/sign-in-as-partner", json={"user_id": target.id})

        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["id"] == target.id
        assert payload["user"]["kind"] == "partner"
        token_payload = decode_token(payload["token"])
        assert token_payload["sub"] == target.id

        audit_row = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "auth.sign_in_as_partner",
                AuditLog.entity_id == target.id,
                AuditLog.changed_by_user_id == actor.id,
            )
        )
        assert audit_row


def test_sign_in_as_partner_rejects_non_admin_roles(db, fixture_data):
    for actor_key in ("l1", "l2", "l3"):
        with api_client(db, fixture_data[actor_key]) as client:
            response = client.post(
                "/api/auth/sign-in-as-partner",
                json={"user_id": fixture_data["responsible_a"].id},
            )
        assert response.status_code == 403


def test_sign_in_as_partner_rejects_partner_actor(db, fixture_data):
    with api_client(db, fixture_data["responsible_a"]) as client:
        response = client.post(
            "/api/auth/sign-in-as-partner",
            json={"user_id": fixture_data["technical_a"].id},
        )
    assert response.status_code == 403


def test_sign_in_as_partner_rejects_internal_target(db, fixture_data):
    with api_client(db, fixture_data["admin"]) as client:
        response = client.post(
            "/api/auth/sign-in-as-partner",
            json={"user_id": fixture_data["l1"].id},
        )
    assert response.status_code == 403


def test_sign_in_as_partner_rejects_inactive_target(db, fixture_data):
    target = fixture_data["responsible_a"]
    target.active = False
    db.flush()
    with api_client(db, fixture_data["admin"]) as client:
        response = client.post("/api/auth/sign-in-as-partner", json={"user_id": target.id})
    assert response.status_code == 403


def test_sign_in_as_partner_service_permission(db, fixture_data):
    try:
        auth.sign_in_as_partner_user(
            db,
            actor=fixture_data["l1"],
            target_user_id=fixture_data["responsible_a"].id,
        )
    except PermissionDenied as exc:
        assert "Admin or Delivery Manager" in str(exc)
    else:
        raise AssertionError("Expected PermissionDenied")
