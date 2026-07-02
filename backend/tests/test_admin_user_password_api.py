from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.core.security import hash_password, verify_password
from ticketmaster.models import AuditLog


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


def test_admin_can_set_partner_user_password(db, fixture_data):
    target_user = fixture_data["technical_a"]
    with api_client(db, fixture_data["admin"]) as client:
        response = client.post(
            f"/api/users/{target_user.id}/password",
            json={"new_password": "StrongerPass123", "confirm_password": "StrongerPass123"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert verify_password("StrongerPass123", target_user.password_hash)
    row = db.scalar(select(AuditLog).where(AuditLog.action == "user.password_set", AuditLog.entity_id == target_user.id))
    assert row


def test_delivery_manager_can_set_non_admin_internal_password(db, fixture_data):
    target_user = fixture_data["l1"]
    assert target_user.password_hash is None

    with api_client(db, fixture_data["dm"]) as client:
        response = client.post(
            f"/api/users/{target_user.id}/password",
            json={"new_password": "DmResetPass123", "confirm_password": "DmResetPass123"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert verify_password("DmResetPass123", target_user.password_hash)


def test_delivery_manager_cannot_set_admin_password(db, fixture_data):
    target_user = fixture_data["admin"]
    with api_client(db, fixture_data["dm"]) as client:
        response = client.post(
            f"/api/users/{target_user.id}/password",
            json={"new_password": "NoAccessPass123", "confirm_password": "NoAccessPass123"},
        )

    assert response.status_code == 403
    assert response.json()["message"] == "Admin role is required"


def test_set_user_password_rejects_confirmation_mismatch(db, fixture_data):
    target_user = fixture_data["responsible_a"]
    with api_client(db, fixture_data["admin"]) as client:
        response = client.post(
            f"/api/users/{target_user.id}/password",
            json={"new_password": "MismatchPass123", "confirm_password": "DifferentPass123"},
        )

    assert response.status_code == 400
    assert response.json()["message"] == "New password and confirmation do not match"


def test_set_user_password_rejects_weak_password(db, fixture_data):
    target_user = fixture_data["responsible_a"]
    with api_client(db, fixture_data["admin"]) as client:
        response = client.post(
            f"/api/users/{target_user.id}/password",
            json={"new_password": "weakpass", "confirm_password": "weakpass"},
        )

    assert response.status_code == 400
    assert response.json()["message"] == "Password must contain at least one number"


def test_set_user_password_rejects_current_password_reuse(db, fixture_data):
    target_user = fixture_data["responsible_a"]
    target_user.password_hash = hash_password("ReusePass123")
    db.flush()

    with api_client(db, fixture_data["admin"]) as client:
        response = client.post(
            f"/api/users/{target_user.id}/password",
            json={"new_password": "ReusePass123", "confirm_password": "ReusePass123"},
        )

    assert response.status_code == 400
    assert response.json()["message"] == "New password must be different from current password"
