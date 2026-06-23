from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.core.security import create_return_token, create_token, decode_token
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


def _sign_in_as_partner(db, fixture_data, actor_key="admin", target_key="responsible_a"):
    actor = fixture_data[actor_key]
    target = fixture_data[target_key]
    with api_client(db, actor) as client:
        response = client.post("/api/auth/sign-in-as-partner", json={"user_id": target.id})
    assert response.status_code == 200
    payload = response.json()
    return payload["token"], payload["return_token"], actor, target


def test_back_to_admin_success(db, fixture_data):
    partner_token, return_token, actor, target = _sign_in_as_partner(db, fixture_data)

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": return_token},
            headers={"Authorization": f"Bearer {partner_token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == actor.id
    assert payload["user"]["kind"] == "internal"
    token_payload = decode_token(payload["token"])
    assert token_payload["sub"] == actor.id

    audit_row = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "auth.back_to_admin",
            AuditLog.entity_id == actor.id,
            AuditLog.changed_by_user_id == target.id,
        )
    )
    assert audit_row


def test_back_to_admin_rejects_reused_return_token(db, fixture_data):
    partner_token, return_token, _actor, _target = _sign_in_as_partner(db, fixture_data)

    with api_client(db) as client:
        first = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": return_token},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": return_token},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
    assert second.status_code == 403
    assert "already used" in second.json()["detail"].lower()


def test_back_to_admin_rejects_forged_return_token(db, fixture_data):
    partner_token, return_token, _actor, _target = _sign_in_as_partner(db, fixture_data)
    forged = return_token[:-4] + "xxxx"

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": forged},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
    assert response.status_code == 403
    assert "signature" in response.json()["detail"].lower()


def test_back_to_admin_rejects_expired_return_token(db, fixture_data):
    actor = fixture_data["admin"]
    target = fixture_data["responsible_a"]
    partner_token = create_token({"sub": target.id})
    expired_return_token = create_return_token(
        impersonator_id=actor.id,
        partner_user_id=target.id,
        ttl_seconds=-60,
    )

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": expired_return_token},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
    assert response.status_code == 403
    assert "expired" in response.json()["detail"].lower()


def test_back_to_admin_rejects_partner_context_mismatch(db, fixture_data):
    partner_token_a, return_token_a, _actor, _target_a = _sign_in_as_partner(
        db, fixture_data, target_key="responsible_a"
    )
    target_b = fixture_data["technical_a"]
    partner_token_b = create_token({"sub": target_b.id})

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": return_token_a},
            headers={"Authorization": f"Bearer {partner_token_b}"},
        )
    assert response.status_code == 403
    assert "does not match" in response.json()["detail"].lower()


def test_back_to_admin_rejects_normal_partner_without_valid_return_token(db, fixture_data):
    target = fixture_data["responsible_a"]
    partner_token = create_token({"sub": target.id})

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": "invalid.return.token"},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
    assert response.status_code == 403


def test_back_to_admin_rejects_internal_actor(db, fixture_data):
    _partner_token, return_token, actor, _target = _sign_in_as_partner(db, fixture_data)
    internal_token = create_token({"sub": actor.id})

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": return_token},
            headers={"Authorization": f"Bearer {internal_token}"},
        )
    assert response.status_code == 403
    assert "partner session" in response.json()["detail"].lower()


def test_back_to_admin_rejects_ineligible_original_account(db, fixture_data):
    partner_token, return_token, actor, target = _sign_in_as_partner(db, fixture_data)
    actor.active = False
    db.flush()

    with api_client(db) as client:
        response = client.post(
            "/api/auth/back-to-admin",
            json={"return_token": return_token},
            headers={"Authorization": f"Bearer {partner_token}"},
        )
    assert response.status_code == 403
    assert "unavailable" in response.json()["detail"].lower()


def test_sign_in_as_partner_includes_return_token(db, fixture_data):
    with api_client(db, fixture_data["admin"]) as client:
        response = client.post(
            "/api/auth/sign-in-as-partner",
            json={"user_id": fixture_data["responsible_a"].id},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("return_token")
    return_payload = decode_token(payload["return_token"])
    assert return_payload["typ"] == "return_admin"
    assert return_payload["imp"] == fixture_data["admin"].id
    assert return_payload["sub"] == fixture_data["responsible_a"].id
