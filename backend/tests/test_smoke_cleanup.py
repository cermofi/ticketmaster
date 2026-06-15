from __future__ import annotations

from sqlalchemy import select

from ticketmaster.models import Client, Partner, Ticket, User
from ticketmaster.services import admin, smoke_cleanup, tickets


def test_marker_cleanup_deletes_only_smoke_marked_ticket(db):
    actor = admin.create_internal_user(db, email="ops@company.test", name="Ops", role="Admin", source="test")
    smoke = tickets.create_internal_ticket(
        db,
        actor=actor,
        ticket_type="Question",
        priority="Normal",
        title="[SMOKE] readiness probe",
        description="Synthetic check",
        source="test",
    )
    real = tickets.create_internal_ticket(
        db,
        actor=actor,
        ticket_type="Question",
        priority="Normal",
        title="Customer issue",
        description="Real ticket",
        source="test",
    )
    db.commit()

    result = smoke_cleanup.cleanup_smoke_artifacts(db, marker_only=True, dry_run=False)
    db.commit()

    assert result["deleted"]["tickets"] == 1
    assert db.get(Ticket, smoke.id) is None
    assert db.get(Ticket, real.id) is not None


def test_include_seed_artifacts_removes_known_seed_entities(db):
    partner = admin.create_partner(db, name="Acme Partner", source="test")
    client = admin.create_client(db, partner_key_or_id=partner.id, name="Acme Bank", source="test")
    responsible = admin.invite_partner_user(
        db,
        partner_key_or_id=partner.id,
        email="responsible@acme.example",
        name="Responsible Partner User",
        role="responsible",
        source="test",
    )
    admin.assign_responsible_to_client(db, client_key_or_id=client.id, user_email_or_id=responsible.id, source="test")
    ticket = tickets.create_partner_ticket(
        db,
        actor=responsible,
        ticket_type="Question",
        priority="Normal",
        title="Seeded partner question",
        description="This ticket is created by seed-dev for local smoke tests.",
        client_id=client.id,
        source="test",
    )
    db.commit()

    result = smoke_cleanup.cleanup_smoke_artifacts(db, marker_only=False, dry_run=False)
    db.commit()

    assert result["deleted"]["tickets"] == 1
    assert db.get(Ticket, ticket.id) is None
    assert db.scalar(select(Partner).where(Partner.key == "acme-partner")) is None
    assert db.scalar(select(Client).where(Client.key == "acme-partner-acme-bank")) is None
    assert db.scalar(select(User).where(User.email == "responsible@acme.example")) is None


def test_dry_run_reports_without_deleting(db):
    actor = admin.create_internal_user(db, email="ops2@company.test", name="Ops", role="Admin", source="test")
    ticket = tickets.create_internal_ticket(
        db,
        actor=actor,
        ticket_type="Question",
        priority="Normal",
        title="[SMOKE] dry run",
        description="Synthetic",
        source="test",
    )
    db.commit()

    result = smoke_cleanup.cleanup_smoke_artifacts(db, marker_only=True, dry_run=True)

    assert result["dry_run"] is True
    assert len(result["discovery"]["tickets"]) == 1
    assert db.get(Ticket, ticket.id) is not None
