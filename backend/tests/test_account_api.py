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


def test_account_me_returns_current_profile(db, fixture_data):
    user = fixture_data["responsible_a"]
    with api_client(db, user) as client:
        response = client.get("/api/account/me")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == user.id
    assert payload["email"] == user.email
    assert payload["name"] == user.name
    assert payload["email_editable"] is False


def test_account_update_name_and_audit(db, fixture_data):
    user = fixture_data["responsible_a"]
    with api_client(db, user) as client:
        response = client.patch("/api/account/me", json={"name": "Responsible Updated"})

    assert response.status_code == 200
    assert user.name == "Responsible Updated"
    row = db.scalar(select(AuditLog).where(AuditLog.action == "account.update", AuditLog.entity_id == user.id))
    assert row
    assert row.old_value == {"name": "Responsible A"}
    assert row.new_value == {"name": "Responsible Updated"}


def test_account_update_forbids_role_changes(db, fixture_data):
    with api_client(db, fixture_data["responsible_a"]) as client:
        response = client.patch("/api/account/me", json={"name": "Nope", "role": "Admin"})

    assert response.status_code == 422


def test_account_update_rejects_email_change(db, fixture_data):
    with api_client(db, fixture_data["responsible_a"]) as client:
        response = client.patch("/api/account/me", json={"email": "new@example.test"})

    assert response.status_code == 400
    assert response.json()["detail"] == "E-mail is used as login identity and cannot be changed here."


def test_account_change_password_success(db, fixture_data):
    user = fixture_data["responsible_a"]
    user.password_hash = hash_password("SecretPass123")
    db.flush()
    with api_client(db, user) as client:
        response = client.post(
            "/api/account/change-password",
            json={
                "current_password": "SecretPass123",
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert verify_password("NewPassword456", user.password_hash)
    row = db.scalar(select(AuditLog).where(AuditLog.action == "account.password_change", AuditLog.entity_id == user.id))
    assert row


def test_account_change_password_wrong_current_password(db, fixture_data):
    user = fixture_data["responsible_a"]
    user.password_hash = hash_password("SecretPass123")
    db.flush()
    with api_client(db, user) as client:
        response = client.post(
            "/api/account/change-password",
            json={
                "current_password": "WrongPassword999",
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Current password is invalid"


def test_account_change_password_rejects_mismatch(db, fixture_data):
    user = fixture_data["responsible_a"]
    user.password_hash = hash_password("SecretPass123")
    db.flush()
    with api_client(db, user) as client:
        response = client.post(
            "/api/account/change-password",
            json={
                "current_password": "SecretPass123",
                "new_password": "NewPassword456",
                "confirm_password": "DifferentPassword456",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "New password and confirmation do not match"


def test_account_change_password_rejects_weak_password(db, fixture_data):
    user = fixture_data["responsible_a"]
    user.password_hash = hash_password("SecretPass123")
    db.flush()
    with api_client(db, user) as client:
        response = client.post(
            "/api/account/change-password",
            json={
                "current_password": "SecretPass123",
                "new_password": "weakpass",
                "confirm_password": "weakpass",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Password must contain at least one number"


def test_account_endpoints_require_authentication(db):
    with api_client(db) as client:
        profile_response = client.get("/api/account/me")
        password_response = client.post(
            "/api/account/change-password",
            json={
                "current_password": "SecretPass123",
                "new_password": "NewPassword456",
                "confirm_password": "NewPassword456",
            },
        )

    assert profile_response.status_code == 403
    assert password_response.status_code == 403
