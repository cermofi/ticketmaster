from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.models import Ticket


def enqueue_ticket_index(ticket_id: str) -> None:
    return None


def index_ticket(db: Session, ticket_id: str) -> None:
    return None


def find_ticket_ids(query: str, *, limit: int = 500) -> list[str] | None:
    return None


def reindex_tickets(db: Session) -> int:
    return len(db.scalars(select(Ticket.id)).all())
