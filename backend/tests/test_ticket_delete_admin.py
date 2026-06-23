from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.models import Attachment, AuditLog, Comment, Ticket, TicketParticipant, TicketWatcher
from ticketmaster.models.entities import new_id
from ticketmaster.services import tickets
from ticketmaster.services.errors import PermissionDenied


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


def create_partner_ticket(db, data):
    ticket = tickets.create_partner_ticket(
        db,
        actor=data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Ticket to delete",
        description="Need help",
        client_id=data["client_a"].id,
        participant_ids=[],
        source="test",
    )
    db.commit()
    return ticket


def test_admin_can_delete_ticket_via_api(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with api_client(db, fixture_data["admin"]) as client:
        response = client.delete(f"/api/tickets/{ticket.id}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": ticket.id}
    assert db.get(Ticket, ticket.id) is None


def test_non_admin_cannot_delete_ticket_via_api(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    for actor in (fixture_data["dm"], fixture_data["l1"], fixture_data["responsible_a"]):
        with api_client(db, actor) as client:
            response = client.delete(f"/api/tickets/{ticket.id}")

        assert response.status_code == 403
        assert db.get(Ticket, ticket.id) is not None


def test_admin_delete_cascades_dependent_data(db, fixture_data, tmp_path):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.add_comment(
        db,
        ticket=ticket,
        actor=fixture_data["responsible_a"],
        body="Follow-up",
        source="test",
    )
    db.add(TicketParticipant(ticket_id=ticket.id, user_id=fixture_data["technical_a"].id))
    db.add(TicketWatcher(ticket_id=ticket.id, user_id=fixture_data["technical_a"].id))
    storage_path = tmp_path / f"{new_id()}.txt"
    storage_path.write_text("payload", encoding="utf-8")
    attachment = Attachment(
        id=new_id(),
        ticket_id=ticket.id,
        comment_id=None,
        uploaded_by_id=fixture_data["admin"].id,
        filename="note.txt",
        content_type="text/plain",
        size_bytes=storage_path.stat().st_size,
        storage_path=str(storage_path),
    )
    db.add(attachment)
    db.commit()

    tickets.delete_ticket(db, ticket=ticket, actor=fixture_data["admin"], source="test")
    db.commit()

    assert db.get(Ticket, ticket.id) is None
    assert db.scalar(select(Comment).where(Comment.ticket_id == ticket.id)) is None
    assert db.scalar(select(TicketParticipant).where(TicketParticipant.ticket_id == ticket.id)) is None
    assert db.scalar(select(TicketWatcher).where(TicketWatcher.ticket_id == ticket.id)) is None
    assert db.get(Attachment, attachment.id) is None
    assert not Path(storage_path).exists()
    delete_audit = db.scalar(
        select(AuditLog).where(AuditLog.entity_id == ticket.id, AuditLog.action == "ticket.delete")
    )
    assert delete_audit is not None
    assert delete_audit.old_value["title"] == "Ticket to delete"


def test_delete_ticket_requires_admin_role(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(PermissionDenied, match="Admin role is required"):
        tickets.delete_ticket(db, ticket=ticket, actor=fixture_data["dm"], source="test")
