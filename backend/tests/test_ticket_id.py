from __future__ import annotations

import re
import uuid
from unittest.mock import patch

import pytest

from ticketmaster.core.ticket_id import (
    MAX_TICKET_ID,
    MIN_TICKET_ID,
    allocate_ticket_id,
    int_to_ticket_id,
    is_standard_ticket_id,
    next_ticket_id,
    ticket_id_to_int,
)
from ticketmaster.models.entities import Ticket
from ticketmaster.services import tickets
from ticketmaster.services.errors import ConflictError


def _make_ticket(db, *, ticket_id: str, fixture_data) -> None:
    db.add(
        Ticket(
            id=ticket_id,
            partner_id=fixture_data["partner_a"].id,
            owner_id=fixture_data["responsible_a"].id,
            created_by_id=fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status="New",
            title=f"Ticket {ticket_id}",
            description=f"Ticket {ticket_id}",
        )
    )


def test_ticket_id_format_helpers() -> None:
    assert is_standard_ticket_id("AAAA")
    assert is_standard_ticket_id("ZZZZ")
    assert not is_standard_ticket_id("aaa")
    assert not is_standard_ticket_id("AAA")
    assert not is_standard_ticket_id("AAAB1")
    assert not is_standard_ticket_id(str(uuid.uuid4()))


def test_ticket_id_progression() -> None:
    assert next_ticket_id("AAAA") == "AAAB"
    assert next_ticket_id("AAAZ") == "AABA"
    assert next_ticket_id("AZZZ") == "BAAA"
    assert next_ticket_id("ZZZY") == "ZZZZ"
    assert next_ticket_id("ZZZZ") is None


def test_ticket_id_int_roundtrip() -> None:
    assert ticket_id_to_int("AAAA") == 0
    assert int_to_ticket_id(0) == "AAAA"
    assert int_to_ticket_id(ticket_id_to_int("ZZZZ")) == "ZZZZ"


def test_allocate_ticket_id_returns_standard_format(db, fixture_data) -> None:
    ticket_id = allocate_ticket_id(db)
    assert re.fullmatch(r"[A-Z]{4}", ticket_id)
    assert is_standard_ticket_id(ticket_id)


def test_create_partner_ticket_uses_random_unique_ids(db, fixture_data) -> None:
    first = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="First",
        description="First ticket",
        source="test",
    )
    second = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Second",
        description="Second ticket",
        source="test",
    )

    assert first.id != second.id
    assert re.fullmatch(r"[A-Z]{4}", first.id)
    assert re.fullmatch(r"[A-Z]{4}", second.id)


def test_allocate_ticket_id_skips_legacy_uuid_rows(db, fixture_data) -> None:
    legacy_id = str(uuid.uuid4())
    db.add(
        Ticket(
            id=legacy_id,
            partner_id=fixture_data["partner_a"].id,
            owner_id=fixture_data["responsible_a"].id,
            created_by_id=fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status="New",
            title="Legacy ticket",
            description="Legacy UUID id",
        )
    )
    db.flush()

    first = allocate_ticket_id(db)
    assert is_standard_ticket_id(first)
    assert first != legacy_id

    _make_ticket(db, ticket_id="AAAC", fixture_data=fixture_data)
    db.flush()

    second = allocate_ticket_id(db)
    assert is_standard_ticket_id(second)
    assert second != "AAAC"


def test_allocate_ticket_id_skips_occupied_slots(db, fixture_data) -> None:
    _make_ticket(db, ticket_id="AAAA", fixture_data=fixture_data)
    _make_ticket(db, ticket_id="AAAB", fixture_data=fixture_data)
    db.flush()

    ticket_id = allocate_ticket_id(db)
    assert ticket_id not in {"AAAA", "AAAB"}
    assert is_standard_ticket_id(ticket_id)


def test_allocate_ticket_id_retries_random_collisions(db, fixture_data, monkeypatch) -> None:
    _make_ticket(db, ticket_id="ZZZZ", fixture_data=fixture_data)
    _make_ticket(db, ticket_id="YYYY", fixture_data=fixture_data)
    db.flush()

    attempts = iter(["ZZZZ", "YYYY", MIN_TICKET_ID])

    def fake_random_ticket_id() -> str:
        return next(attempts)

    monkeypatch.setattr("ticketmaster.core.ticket_id._random_ticket_id", fake_random_ticket_id)

    assert allocate_ticket_id(db) == MIN_TICKET_ID


def test_allocate_ticket_id_uses_deterministic_fallback(db, fixture_data, monkeypatch) -> None:
    _make_ticket(db, ticket_id="AAAA", fixture_data=fixture_data)
    db.flush()

    monkeypatch.setattr("ticketmaster.core.ticket_id._MAX_RANDOM_ATTEMPTS", 0)

    assert allocate_ticket_id(db) == "AAAB"


def test_allocate_ticket_id_exhaustion(db, fixture_data, monkeypatch) -> None:
    monkeypatch.setattr("ticketmaster.core.ticket_id.TICKET_ID_SPACE_SIZE", 2)

    _make_ticket(db, ticket_id=int_to_ticket_id(0), fixture_data=fixture_data)
    _make_ticket(db, ticket_id=int_to_ticket_id(1), fixture_data=fixture_data)
    db.flush()

    with pytest.raises(ConflictError, match="Ticket ID space exhausted"):
        allocate_ticket_id(db)


def test_allocate_ticket_id_exhaustion_when_last_code_taken(db, fixture_data, monkeypatch) -> None:
    monkeypatch.setattr("ticketmaster.core.ticket_id.TICKET_ID_SPACE_SIZE", 1)

    _make_ticket(db, ticket_id=MAX_TICKET_ID, fixture_data=fixture_data)
    db.flush()

    with pytest.raises(ConflictError, match="Ticket ID space exhausted"):
        allocate_ticket_id(db)


def test_all_create_flows_use_standard_ticket_ids(db, fixture_data) -> None:
    partner_ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Partner",
        description="Partner ticket",
        source="test",
    )
    on_behalf_ticket = tickets.create_partner_ticket_on_behalf(
        db,
        actor=fixture_data["dm"],
        partner_id=fixture_data["partner_a"].id,
        owner_ref=fixture_data["responsible_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="On behalf",
        description="On behalf ticket",
        source="test",
    )
    internal_ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["l1"],
        ticket_type="Question",
        priority="Normal",
        title="Internal",
        description="Internal ticket",
        source="test",
    )
    system_ticket = tickets.create_system_ticket(
        db,
        partner_id=fixture_data["partner_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="System",
        description="System ticket",
        source="test",
    )

    created_ids = [partner_ticket.id, on_behalf_ticket.id, internal_ticket.id, system_ticket.id]
    assert len(set(created_ids)) == len(created_ids)
    for ticket_id in created_ids:
        assert is_standard_ticket_id(ticket_id)


def test_allocate_ticket_id_random_distribution(db, fixture_data) -> None:
    with patch("ticketmaster.core.ticket_id._random_ticket_id", side_effect=lambda: "QQQQ"):
        assert allocate_ticket_id(db) == "QQQQ"
