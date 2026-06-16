from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.models.entities import Ticket
from ticketmaster.services.errors import ConflictError

TICKET_ID_PATTERN = re.compile(r"^[A-Z]{4}$")
MIN_TICKET_ID = "AAAA"
MAX_TICKET_ID = "ZZZZ"
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_standard_ticket_id(value: str) -> bool:
    return bool(TICKET_ID_PATTERN.fullmatch(value))


def ticket_id_to_int(code: str) -> int:
    value = 0
    for char in code:
        value = value * 26 + (_ALPHABET.index(char))
    return value


def int_to_ticket_id(value: int) -> str:
    chars: list[str] = []
    remaining = value
    for _ in range(4):
        remaining, index = divmod(remaining, 26)
        chars.append(_ALPHABET[index])
    return "".join(reversed(chars))


def next_ticket_id(code: str) -> str | None:
    if not is_standard_ticket_id(code):
        raise ValueError(f"Invalid ticket ID: {code}")
    next_value = ticket_id_to_int(code) + 1
    if next_value > ticket_id_to_int(MAX_TICKET_ID):
        return None
    return int_to_ticket_id(next_value)


def allocate_ticket_id(db: Session) -> str:
    existing_ids = db.scalars(select(Ticket.id)).all()
    standard_ids = [ticket_id for ticket_id in existing_ids if is_standard_ticket_id(ticket_id)]
    if standard_ids:
        candidate = next_ticket_id(max(standard_ids))
    else:
        candidate = MIN_TICKET_ID
    if candidate is None:
        raise ConflictError("Ticket ID space exhausted (ZZZZ reached)")

    while db.get(Ticket, candidate) is not None:
        candidate = next_ticket_id(candidate)
        if candidate is None:
            raise ConflictError("Ticket ID space exhausted (ZZZZ reached)")

    return candidate
