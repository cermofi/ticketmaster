from __future__ import annotations

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.models.entities import Ticket
from ticketmaster.services.errors import ConflictError

TICKET_ID_PATTERN = re.compile(r"^[A-Z]{4}$")
MIN_TICKET_ID = "AAAA"
MAX_TICKET_ID = "ZZZZ"
_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TICKET_ID_SPACE_SIZE = 26**4
_MAX_RANDOM_ATTEMPTS = 64


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


def _random_ticket_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))


def _load_used_standard_ids(db: Session) -> set[str]:
    existing_ids = db.scalars(select(Ticket.id)).all()
    return {ticket_id for ticket_id in existing_ids if is_standard_ticket_id(ticket_id)}


def _is_ticket_id_available(db: Session, candidate: str, used_standard_ids: set[str]) -> bool:
    if candidate in used_standard_ids:
        return False
    return db.get(Ticket, candidate) is None


def allocate_ticket_id(db: Session) -> str:
    used_standard_ids = _load_used_standard_ids(db)
    if len(used_standard_ids) >= TICKET_ID_SPACE_SIZE:
        raise ConflictError("Ticket ID space exhausted (all [A-Z]{4} codes in use)")

    for _ in range(_MAX_RANDOM_ATTEMPTS):
        candidate = _random_ticket_id()
        if _is_ticket_id_available(db, candidate, used_standard_ids):
            return candidate
        if is_standard_ticket_id(candidate):
            used_standard_ids.add(candidate)

    for value in range(TICKET_ID_SPACE_SIZE):
        candidate = int_to_ticket_id(value)
        if _is_ticket_id_available(db, candidate, used_standard_ids):
            return candidate
        used_standard_ids.add(candidate)

    raise ConflictError("Ticket ID space exhausted (all [A-Z]{4} codes in use)")
