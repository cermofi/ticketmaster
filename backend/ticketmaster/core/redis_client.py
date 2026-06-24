from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ticketmaster.core.config import settings

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger("ticketmaster.redis")

_client: Redis | None = None
_checked = False
_available = False
_fallback_logged = False


def redis_configured() -> bool:
    return bool(settings.redis_url)


def redis_available() -> bool:
    global _checked, _available
    if not redis_configured():
        return False
    if _checked:
        return _available
    _checked = True
    try:
        client = get_redis()
        client.ping()
        _available = True
    except Exception as exc:
        logger.warning("Redis unavailable, using in-memory fallback: %s", exc)
        _available = False
    return _available


def get_redis() -> Redis:
    global _client
    if _client is None:
        if not settings.redis_url:
            raise RuntimeError("REDIS_URL is not configured")
        import redis

        _client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.redis_socket_timeout_seconds,
            socket_timeout=settings.redis_socket_timeout_seconds,
        )
    return _client


def log_redis_fallback_once(feature: str) -> None:
    global _fallback_logged
    if _fallback_logged:
        return
    _fallback_logged = True
    logger.warning("Redis fallback active for %s (REDIS_URL unset or unreachable)", feature)


def reset_redis_state_for_tests() -> None:
    global _client, _checked, _available, _fallback_logged
    _client = None
    _checked = False
    _available = False
    _fallback_logged = False
