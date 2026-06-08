from __future__ import annotations

import logging

import redis

from ticketmaster.core.config import settings


logger = logging.getLogger("ticketmaster.redis")
_client: redis.Redis | None = None


def reset_redis() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None


def get_redis() -> redis.Redis | None:
    global _client
    if not settings.redis_url:
        return None
    if _client is None:
        try:
            socket_timeout = max(settings.queue_poll_timeout_seconds + 5, 10)
            _client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=socket_timeout,
                health_check_interval=30,
            )
            _client.ping()
        except Exception as exc:
            logger.warning("redis unavailable: %s", exc)
            _client = None
    return _client
