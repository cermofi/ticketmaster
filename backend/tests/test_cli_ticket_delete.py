from __future__ import annotations

import io
from contextlib import contextmanager, redirect_stderr, redirect_stdout

from ticketmaster.cli.main import main
from ticketmaster.models import Ticket
from ticketmaster.services import tickets


@contextmanager
def mock_session_scope(db):
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def create_partner_ticket(db, data):
    ticket = tickets.create_partner_ticket(
        db,
        actor=data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="CLI delete target",
        description="Need help",
        client_id=data["client_a"].id,
        participant_ids=[],
        source="test",
    )
    db.commit()
    return ticket


def test_ticket_delete_cli_requires_confirm(db, fixture_data, monkeypatch):
    ticket = create_partner_ticket(db, fixture_data)
    monkeypatch.setattr("ticketmaster.cli.main.session_scope", lambda: mock_session_scope(db))

    exit_code = main(["ticket", "delete", "--id", ticket.id])
    assert exit_code == 1
    assert db.get(Ticket, ticket.id) is not None


def test_ticket_delete_cli_dry_run(db, fixture_data, monkeypatch):
    ticket = create_partner_ticket(db, fixture_data)
    monkeypatch.setattr("ticketmaster.cli.main.session_scope", lambda: mock_session_scope(db))
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        exit_code = main(["ticket", "delete", "--id", ticket.id, "--dry-run"])

    assert exit_code == 0
    assert '"dry_run": true' in buffer.getvalue()
    assert db.get(Ticket, ticket.id) is not None


def test_ticket_delete_cli_confirm_deletes(db, fixture_data, monkeypatch):
    ticket = create_partner_ticket(db, fixture_data)
    monkeypatch.setattr("ticketmaster.cli.main.session_scope", lambda: mock_session_scope(db))
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        exit_code = main(["ticket", "delete", "--id", ticket.id, "--confirm"])

    assert exit_code == 0
    assert db.get(Ticket, ticket.id) is None
    assert "ticket.delete actor=" in stderr.getvalue()
