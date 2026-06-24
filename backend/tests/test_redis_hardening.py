from __future__ import annotations

import pytest

from ticketmaster.core import redis_client
from ticketmaster.core.config import PRODUCTION_HOST, PRODUCTION_ORIGIN, settings
from ticketmaster.core.security import create_return_token, decode_and_consume_return_token
from ticketmaster.services import redis_store
from ticketmaster.services.rate_limit import (
    auth_rate_limit_key,
    check_rate_limit,
    clear_rate_limit,
    list_rate_limit_keys,
    reset_rate_limits,
)


@pytest.fixture()
def fake_redis(monkeypatch):
    import fakeredis
    from dataclasses import replace

    from ticketmaster.core import security
    from ticketmaster.services import rate_limit as rate_limit_service

    client = fakeredis.FakeRedis(decode_responses=True)
    patched_settings = replace(settings, redis_url="redis://fake/0")
    for module in (redis_client, redis_store, rate_limit_service, security):
        monkeypatch.setattr(module, "settings", patched_settings, raising=False)
    monkeypatch.setattr(redis_client, "_client", client, raising=False)
    monkeypatch.setattr(redis_client, "_checked", True, raising=False)
    monkeypatch.setattr(redis_client, "_available", True, raising=False)
    monkeypatch.setattr(redis_client, "_fallback_logged", False, raising=False)
    client.flushdb()
    yield client
    redis_client.reset_redis_state_for_tests()


def test_production_host_constants():
    assert PRODUCTION_HOST == "ticketmaster.cermofi.cz"
    assert PRODUCTION_ORIGIN == "https://ticketmaster.cermofi.cz"


def test_redis_rate_limit_blocks_after_threshold(fake_redis, monkeypatch):
    from dataclasses import replace

    from ticketmaster.services import rate_limit as rate_limit_service
    from ticketmaster.services.errors import RateLimitError

    patched = replace(settings, redis_url="redis://fake/0", auth_rate_limit_attempts=2, auth_rate_limit_window_seconds=300)
    for module in (redis_store, rate_limit_service):
        monkeypatch.setattr(module, "settings", patched, raising=False)
    key = auth_rate_limit_key("login", "203.0.113.10", "user@example.test")
    reset_rate_limits(scope="login")

    check_rate_limit(key)
    check_rate_limit(key)
    with pytest.raises(RateLimitError, match="Too many"):
        check_rate_limit(key)


def test_redis_rate_limit_clear_and_list(fake_redis):
    key = auth_rate_limit_key("login", "203.0.113.10", "user@example.test")
    reset_rate_limits(scope="login")
    check_rate_limit(key)
    assert key in list_rate_limit_keys()
    assert clear_rate_limit(key) is True
    assert key not in list_rate_limit_keys()


def test_redis_return_jti_one_time_use(fake_redis, monkeypatch):
    token = create_return_token(impersonator_id="admin-id", partner_user_id="partner-id", ttl_seconds=600)
    payload = decode_and_consume_return_token(token)
    assert payload["typ"] == "return_admin"

    with pytest.raises(ValueError, match="already used"):
        decode_and_consume_return_token(token)


def test_in_memory_fallback_when_redis_unreachable(monkeypatch):
    from dataclasses import replace

    from ticketmaster.services import rate_limit as rate_limit_service
    from ticketmaster.services.errors import RateLimitError

    redis_client.reset_redis_state_for_tests()
    patched = replace(
        settings,
        redis_url="redis://127.0.0.1:6399/0",
        auth_rate_limit_attempts=2,
        auth_rate_limit_window_seconds=300,
    )
    for module in (redis_client, redis_store, rate_limit_service):
        monkeypatch.setattr(module, "settings", patched, raising=False)
    reset_rate_limits(scope="login")
    key = auth_rate_limit_key("login", "203.0.113.10", "fallback@example.test")

    check_rate_limit(key)
    check_rate_limit(key)
    with pytest.raises(RateLimitError, match="Too many"):
        check_rate_limit(key)

    redis_client.reset_redis_state_for_tests()
