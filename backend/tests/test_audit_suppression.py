from __future__ import annotations

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ticketmaster.api.deps import current_user, get_db
from ticketmaster.api.main import app
from ticketmaster.core.config import settings
from ticketmaster.models import AuditLog
from ticketmaster.services import admin, audit as audit_service, tickets
from ticketmaster.services.audit_context import suppress_audit

# Legacy smoke header — must not suppress audit on public API requests.
SMOKE_REQUEST_HEADERS = {"x-ticketmaster-smoke": "1"}


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


def _audit_count(db) -> int:
    return db.scalar(select(func.count()).select_from(AuditLog)) or 0


def test_audit_writes_when_not_suppressed(db, fixture_data):
    before = _audit_count(db)
    audit_service.audit(
        db,
        entity_type="Auth",
        entity_id=fixture_data["admin"].id,
        action="auth.login",
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()
    assert _audit_count(db) == before + 1


def test_suppress_audit_context_skips_writes(db, fixture_data):
    before = _audit_count(db)
    with suppress_audit():
        audit_service.audit(
            db,
            entity_type="Auth",
            entity_id=fixture_data["admin"].id,
            action="auth.login",
            actor=fixture_data["admin"],
            source="test",
        )
        tickets.create_internal_ticket(
            db,
            actor=fixture_data["admin"],
            ticket_type="Question",
            priority="Normal",
            title="[SMOKE] suppressed create",
            description="Should not audit",
            source="test",
        )
    db.commit()
    assert _audit_count(db) == before


def test_normal_login_still_audits(db, fixture_data):
    admin.ensure_dev_login_password(fixture_data["admin"])
    db.commit()
    before = _audit_count(db)

    with api_client(db) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": fixture_data["admin"].email, "password": settings.dev_password},
        )

    assert response.status_code == 200
    assert _audit_count(db) == before + 1


def test_smoke_header_does_not_skip_login_audit(db, fixture_data):
    admin.ensure_dev_login_password(fixture_data["admin"])
    db.commit()
    before = _audit_count(db)

    with api_client(db) as client:
        response = client.post(
            "/api/auth/login",
            json={"email": fixture_data["admin"].email, "password": settings.dev_password},
            headers=SMOKE_REQUEST_HEADERS,
        )

    assert response.status_code == 200
    assert _audit_count(db) == before + 1


def test_smoke_header_does_not_skip_export_audit(db, fixture_data):
    before = _audit_count(db)

    with api_client(db, fixture_data["admin"]) as client:
        response = client.get("/api/tickets/export?format=xlsx&limit=1", headers=SMOKE_REQUEST_HEADERS)

    assert response.status_code == 200
    assert _audit_count(db) == before + 1


def test_normal_export_still_audits(db, fixture_data):
    before = _audit_count(db)

    with api_client(db, fixture_data["admin"]) as client:
        response = client.get("/api/tickets/export?format=xlsx&limit=1")

    assert response.status_code == 200
    assert _audit_count(db) == before + 1
