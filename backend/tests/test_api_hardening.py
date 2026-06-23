from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

from fastapi.testclient import TestClient

from ticketmaster.api.deps import get_db
from ticketmaster.api.main import app
from ticketmaster.core.config import settings
from ticketmaster.services import admin
from ticketmaster.services import rate_limit as rate_limit_service
from ticketmaster.services.rate_limit import auth_rate_limit_key, check_rate_limit, reset_rate_limits


@contextmanager
def api_client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_unified_error_payload_for_permission_denied(db, fixture_data):
    admin.ensure_dev_login_password(fixture_data["admin"])
    db.commit()
    reset_rate_limits(scope="login")

    with api_client(db) as client:
        response = client.post("/api/auth/login", json={"email": fixture_data["admin"].email, "password": "wrong-password"})

    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "permission_denied"
    assert payload["message"]
    assert "request_id" in payload
    assert response.headers.get("X-Request-ID") == payload["request_id"]


def test_unified_error_payload_for_rate_limit(db, fixture_data, monkeypatch):
    monkeypatch.setattr(
        rate_limit_service,
        "settings",
        replace(settings, auth_rate_limit_attempts=2, auth_rate_limit_window_seconds=300),
    )
    reset_rate_limits(scope="login")

    with api_client(db) as client:
        for _ in range(2):
            client.post("/api/auth/login", json={"email": "blocked@example.test", "password": "x"})
        response = client.post("/api/auth/login", json={"email": "blocked@example.test", "password": "x"})

    assert response.status_code == 429
    payload = response.json()
    assert payload["code"] == "rate_limit_exceeded"
    assert "Too many" in payload["message"]
    assert payload["request_id"]


def test_rate_limit_reset_by_scope():
    key = auth_rate_limit_key("login", "203.0.113.10", "user@example.test")
    check_rate_limit(key)
    assert reset_rate_limits(scope="login", ip="203.0.113.10", identifier="user@example.test") == 1


def test_respects_incoming_request_id_header(db):
    with api_client(db) as client:
        response = client.get("/api/health", headers={"X-Request-ID": "test-req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-req-123"
    assert response.json()["status"] == "ok"
