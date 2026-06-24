from __future__ import annotations

import time
from typing import Iterable

from ticketmaster.core.config import settings
from ticketmaster.core.redis_client import get_redis, redis_available, redis_configured

_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 1
"""
_rate_limit_script_sha: str | None = None


def rate_limit_key(key: str) -> str:
    return f"rl:{key}"


def return_jti_key(jti: str) -> str:
    return f"rtj:{jti}"


def redis_check_rate_limit(key: str) -> bool:
    """Return True when attempt is allowed, False when limit exceeded."""
    client = get_redis()
    full_key = rate_limit_key(key)
    now = time.time()
    window = settings.auth_rate_limit_window_seconds
    limit = settings.auth_rate_limit_attempts
    member = f"{now:.6f}:{time.time_ns()}"

    global _rate_limit_script_sha
    try:
        if _rate_limit_script_sha is None:
            _rate_limit_script_sha = client.script_load(_RATE_LIMIT_SCRIPT)
        allowed = client.evalsha(
            _rate_limit_script_sha,
            1,
            full_key,
            str(now),
            str(window),
            str(limit),
            member,
        )
        return bool(allowed)
    except Exception:
        pipe = client.pipeline()
        pipe.zremrangebyscore(full_key, 0, now - window)
        pipe.zcard(full_key)
        _, count = pipe.execute()
        if count >= limit:
            return False
        client.zadd(full_key, {member: now})
        client.expire(full_key, window + 1)
        return True


def redis_clear_rate_limit(key: str) -> bool:
    return get_redis().delete(rate_limit_key(key)) > 0


def redis_reset_rate_limits(
    *,
    ip: str | None = None,
    identifier: str | None = None,
    scope: str | None = None,
) -> int:
    client = get_redis()
    removed = 0
    for redis_key in _scan_keys(client, "rl:*"):
        logical_key = redis_key[3:]
        parts = logical_key.split(":", 2)
        if len(parts) != 3:
            continue
        key_scope, key_ip, key_identifier = parts
        if scope and key_scope != scope:
            continue
        if ip and key_ip != ip:
            continue
        if identifier and key_identifier != identifier.strip().lower():
            continue
        removed += client.delete(redis_key)
    return removed


def redis_list_rate_limit_keys() -> list[str]:
    client = get_redis()
    return sorted(key[3:] for key in _scan_keys(client, "rl:*"))


def redis_consume_return_jti(jti: str, ttl_seconds: int) -> bool:
    """Return True when JTI was consumed for the first time."""
    ttl = max(1, int(ttl_seconds))
    return bool(get_redis().set(return_jti_key(jti), "1", nx=True, ex=ttl))


def redis_return_jti_exists(jti: str) -> bool:
    return bool(get_redis().exists(return_jti_key(jti)))


def redis_enabled() -> bool:
    return redis_configured() and redis_available()


def _scan_keys(client, pattern: str) -> Iterable[str]:
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=200)
        yield from keys
        if cursor == 0:
            break
