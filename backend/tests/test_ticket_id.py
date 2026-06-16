from __future__ import annotations

import re
import uuid

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


def test_allocate_ticket_id_starts_at_aaaa(db, fixture_data) -> None:
    ticket_id = allocate_ticket_id(db)
    assert ticket_id == "AAAA"
    assert re.fullmatch(r"[A-Z]{4}", ticket_id)


def test_create_partner_ticket_uses_sequential_ids(db, fixture_data) -> None:
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

    assert first.id == "AAAA"
    assert second.id == "AAAB"
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

    assert allocate_ticket_id(db) == MIN_TICKET_ID

    db.add(
        Ticket(
            id="AAAC",
            partner_id=fixture_data["partner_a"].id,
            owner_id=fixture_data["responsible_a"].id,
            created_by_id=fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status="New",
            title="Standard ticket",
            description="Existing AAAA-format id",
        )
    )
    db.flush()

    assert allocate_ticket_id(db) == "AAAD"


def test_allocate_ticket_id_skips_occupied_slots(db, fixture_data) -> None:
    db.add(
        Ticket(
            id="AAAA",
            partner_id=fixture_data["partner_a"].id,
            owner_id=fixture_data["responsible_a"].id,
            created_by_id=fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status="New",
            title="First",
            description="First",
        )
    )
    db.add(
        Ticket(
            id="AAAB",
            partner_id=fixture_data["partner_a"].id,
            owner_id=fixture_data["responsible_a"].id,
            created_by_id=fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status="New",
            title="Occupied next slot",
            description="Occupied next slot",
        )
    )
    db.flush()

    assert allocate_ticket_id(db) == "AAAC"


def test_allocate_ticket_id_exhaustion(db, fixture_data) -> None:
    db.add(
        Ticket(
            id=MAX_TICKET_ID,
            partner_id=fixture_data["partner_a"].id,
            owner_id=fixture_data["responsible_a"].id,
            created_by_id=fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status="New",
            title="Last ticket",
            description="Last ticket",
        )
    )
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

    assert [partner_ticket.id, on_behalf_ticket.id, internal_ticket.id, system_ticket.id] == [
        "AAAA",
        "AAAB",
        "AAAC",
        "AAAD",
    ]
    for ticket_id in (partner_ticket.id, on_behalf_ticket.id, internal_ticket.id, system_ticket.id):
        assert is_standard_ticket_id(ticket_id)
