from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from ticketmaster.models import AuditLog, User
from ticketmaster.services import audit as audit_service
from ticketmaster.services import tickets
from ticketmaster.services.audit_display import (
    enrich_audit_row,
    enrich_audit_rows,
    format_audit_datetime,
    user_display_label,
)


def test_format_audit_datetime_uses_prague_timezone_with_seconds():
    value = datetime(2026, 6, 2, 11, 11, 7, tzinfo=timezone.utc)
    assert format_audit_datetime(value) == "02.06.2026 13:11:07"


def test_user_display_label_prefers_name_and_email():
    user = User(id="u1", email="admin@example.test", name="Admin", kind="internal")
    assert user_display_label(user) == "Admin (admin@example.test)"


def test_enrich_audit_rows_resolves_ticket_and_actor(db, fixture_data):
    ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Need help with export",
        description="Details",
        client_id=fixture_data["client_a"].id,
        participant_ids=[],
        source="test",
    )
    db.commit()

    rows = list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "Ticket", AuditLog.entity_id == ticket.id)).all())
    enriched = enrich_audit_rows(db, rows)
    create_row = next(row for row in enriched if row["action"] == "ticket.create")

    assert create_row["changed_by_label"] == "Responsible A (responsible-a@example.test)"
    assert create_row["entity_label"].startswith("Ticket ")
    assert "Need help with export" in create_row["entity_label"]
    assert create_row["changed_at_display"] is not None


def test_enrich_audit_row_auth_email_entity(db):
    audit_service.audit(
        db,
        entity_type="Auth",
        entity_id="someone@example.test",
        action="auth.login_failed",
        source="ui",
        new_value={"method": "password"},
    )
    db.commit()

    row = db.scalars(select(AuditLog).order_by(AuditLog.changed_at.desc())).first()
    enriched = enrich_audit_row(
        db,
        row,
        {
            "users_by_id": {},
            "tickets_by_id": {},
            "partners_by_id": {},
            "clients_by_id": {},
            "comments_by_id": {},
            "attachments_by_id": {},
        },
    )

    assert enriched["entity_label"] == "Auth someone@example.test"
    assert enriched["changed_by_label"] == "UI"
