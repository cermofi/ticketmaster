from __future__ import annotations

import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import Comment, Ticket


logger = logging.getLogger("ticketmaster.search")


def enqueue_ticket_index(ticket_id: str) -> None:
    try:
        from ticketmaster.services.jobs import enqueue_job

        enqueue_job("search.index_ticket", {"ticket_id": ticket_id})
    except Exception as exc:
        logger.warning("search enqueue failed ticket_id=%s error=%s", ticket_id, exc)


def index_ticket(db: Session, ticket_id: str) -> None:
    if not settings.elasticsearch_enabled:
        return
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        return
    _ensure_index()
    comments = db.scalars(
        select(Comment.body).where(
            Comment.ticket_id == ticket.id,
            Comment.deleted_at.is_(None),
            Comment.visibility == "comment",
        )
    ).all()
    document = {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "comments": "\n".join(comments),
        "status": ticket.status,
        "priority": ticket.priority,
        "type": ticket.type,
        "resolver_team": ticket.resolver_team,
        "partner_id": ticket.partner_id,
        "client_id": ticket.client_id,
        "owner_id": ticket.owner_id,
        "assignee_id": ticket.assignee_id,
        "internal": ticket.internal,
        "updated_at": _iso(ticket.updated_at),
        "created_at": _iso(ticket.created_at),
    }
    with httpx.Client(timeout=5) as client:
        response = client.put(f"{settings.elasticsearch_url}/{settings.elasticsearch_index}/_doc/{ticket.id}", json=document)
        response.raise_for_status()


def find_ticket_ids(query: str, *, limit: int = 500) -> list[str] | None:
    if not settings.elasticsearch_enabled or not query.strip():
        return None
    body = {
        "size": limit,
        "_source": False,
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^3", "description^2", "comments"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        },
    }
    try:
        with httpx.Client(timeout=3) as client:
            response = client.post(f"{settings.elasticsearch_url}/{settings.elasticsearch_index}/_search", json=body)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return [hit["_id"] for hit in response.json().get("hits", {}).get("hits", [])]
    except Exception as exc:
        logger.warning("elasticsearch search failed: %s", exc)
        return None


def reindex_tickets(db: Session) -> int:
    count = 0
    for ticket_id in db.scalars(select(Ticket.id)).all():
        index_ticket(db, ticket_id)
        count += 1
    return count


def _ensure_index() -> None:
    mapping = {
        "mappings": {
            "properties": {
                "title": {"type": "text"},
                "description": {"type": "text"},
                "comments": {"type": "text"},
                "status": {"type": "keyword"},
                "priority": {"type": "keyword"},
                "type": {"type": "keyword"},
                "resolver_team": {"type": "keyword"},
                "partner_id": {"type": "keyword"},
                "client_id": {"type": "keyword"},
                "owner_id": {"type": "keyword"},
                "assignee_id": {"type": "keyword"},
                "internal": {"type": "boolean"},
                "updated_at": {"type": "date"},
                "created_at": {"type": "date"},
            }
        }
    }
    with httpx.Client(timeout=5) as client:
        response = client.put(f"{settings.elasticsearch_url}/{settings.elasticsearch_index}", json=mapping)
        if response.status_code not in {200, 400}:
            response.raise_for_status()


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
