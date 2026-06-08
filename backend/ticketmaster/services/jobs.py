from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.core.database import SessionLocal
from ticketmaster.services import notifications, search
from ticketmaster.services.redis_client import get_redis, reset_redis


logger = logging.getLogger("ticketmaster.jobs")


@dataclass
class Job:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


def enqueue_job(kind: str, payload: dict[str, Any] | None = None) -> bool:
    if not settings.queue_enabled:
        return False
    client = get_redis()
    if client is None:
        return False
    body = json.dumps({"kind": kind, "payload": payload or {}}, separators=(",", ":"))
    client.lpush(settings.queue_name, body)
    return True


def worker_loop() -> None:
    logger.info("worker starting queue=%s", settings.queue_name)
    next_retry = 0.0
    while True:
        now = time.monotonic()
        if now >= next_retry:
            _run_with_session(Job(kind="notifications.retry_failed"))
            next_retry = now + settings.worker_retry_interval_seconds

        client = get_redis()
        if client is None:
            time.sleep(settings.queue_poll_timeout_seconds)
            continue
        try:
            item = client.brpop(settings.queue_name, timeout=settings.queue_poll_timeout_seconds)
        except redis.RedisError as exc:
            logger.warning("redis queue read failed: %s", exc)
            reset_redis()
            time.sleep(min(settings.queue_poll_timeout_seconds, 5))
            continue
        if not item:
            continue
        _, raw = item
        try:
            parsed = json.loads(raw)
            _run_with_session(Job(kind=parsed["kind"], payload=parsed.get("payload") or {}))
        except Exception:
            logger.exception("job failed raw=%s", raw)


def _run_with_session(job: Job) -> None:
    db = SessionLocal()
    try:
        _run_job(db, job)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("job failed kind=%s payload=%s", job.kind, job.payload)
    finally:
        db.close()


def _run_job(db: Session, job: Job) -> None:
    if job.kind == "notifications.retry_failed":
        sent = notifications.retry_failed(db)
        if sent:
            logger.info("notifications sent count=%s", sent)
        return
    if job.kind == "search.index_ticket":
        search.index_ticket(db, job.payload["ticket_id"])
        return
    if job.kind == "search.reindex_tickets":
        search.reindex_tickets(db)
        return
    logger.warning("unknown job kind=%s", job.kind)
