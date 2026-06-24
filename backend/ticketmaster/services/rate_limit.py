from __future__ import annotations

import time

from ticketmaster.core.config import settings
from ticketmaster.core.redis_client import log_redis_fallback_once, redis_configured
from ticketmaster.services.errors import RateLimitError
from ticketmaster.services import redis_store

_attempts: dict[str, list[float]] = {}


def auth_rate_limit_key(scope: str, client_ip: str, identifier: str) -> str:
    return f"{scope}:{client_ip}:{identifier.strip().lower()}"


def check_rate_limit(key: str) -> None:
    if redis_store.redis_enabled():
        if not redis_store.redis_check_rate_limit(key):
            raise RateLimitError("Too many authentication attempts")
        return

    if redis_configured():
        log_redis_fallback_once("auth rate limit")

    now = time.time()
    window_start = now - settings.auth_rate_limit_window_seconds
    attempts = [stamp for stamp in _attempts.get(key, []) if stamp >= window_start]
    if len(attempts) >= settings.auth_rate_limit_attempts:
        raise RateLimitError("Too many authentication attempts")
    attempts.append(now)
    _attempts[key] = attempts


def clear_rate_limit(key: str) -> bool:
    if redis_store.redis_enabled():
        return redis_store.redis_clear_rate_limit(key)

    if redis_configured():
        log_redis_fallback_once("auth rate limit")
    return _attempts.pop(key, None) is not None


def reset_rate_limits(*, ip: str | None = None, identifier: str | None = None, scope: str | None = None) -> int:
    if redis_store.redis_enabled():
        return redis_store.redis_reset_rate_limits(ip=ip, identifier=identifier, scope=scope)

    if redis_configured():
        log_redis_fallback_once("auth rate limit")

    if not ip and not identifier and not scope:
        count = len(_attempts)
        _attempts.clear()
        return count

    removed = 0
    for key in list(_attempts):
        parts = key.split(":", 2)
        if len(parts) != 3:
            continue
        key_scope, key_ip, key_identifier = parts
        if scope and key_scope != scope:
            continue
        if ip and key_ip != ip:
            continue
        if identifier and key_identifier != identifier.strip().lower():
            continue
        _attempts.pop(key, None)
        removed += 1
    return removed


def list_rate_limit_keys() -> list[str]:
    if redis_store.redis_enabled():
        return redis_store.redis_list_rate_limit_keys()

    if redis_configured():
        log_redis_fallback_once("auth rate limit")
    return sorted(_attempts)
