from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from ticketmaster.core.config import settings
from ticketmaster.core.redis_client import log_redis_fallback_once, redis_configured


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, salt_hex, digest_hex = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return hmac.compare_digest(actual, expected)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_token(payload: dict[str, Any], ttl_seconds: int = 12 * 60 * 60) -> str:
    body = dict(payload)
    body["exp"] = int(time.time()) + ttl_seconds
    encoded = _b64(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(settings.app_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64(signature)}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("Invalid bearer token format") from exc
    expected = hmac.new(settings.app_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_unb64(signature), expected):
        raise ValueError("Invalid bearer token signature")
    payload = json.loads(_unb64(encoded))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Bearer token expired")
    return payload


RETURN_TOKEN_TYP = "return_admin"
_consumed_return_jtis: dict[str, float] = {}


def _purge_consumed_return_jtis() -> None:
    now = time.time()
    for jti, expires_at in list(_consumed_return_jtis.items()):
        if expires_at < now:
            del _consumed_return_jtis[jti]


def _consume_return_jti(jti: str, expires_at: float) -> None:
    from ticketmaster.services import redis_store

    ttl_seconds = max(1, int(expires_at - time.time()))
    if redis_store.redis_enabled():
        if not redis_store.redis_consume_return_jti(jti, ttl_seconds):
            raise ValueError("Return token already used")
        return

    if redis_configured():
        log_redis_fallback_once("return-token JTI anti-replay")

    _purge_consumed_return_jtis()
    if jti in _consumed_return_jtis:
        raise ValueError("Return token already used")
    _consumed_return_jtis[jti] = expires_at


def create_return_token(*, impersonator_id: str, partner_user_id: str, ttl_seconds: int = 12 * 60 * 60) -> str:
    jti = _b64(os.urandom(16))
    return create_token(
        {
            "typ": RETURN_TOKEN_TYP,
            "imp": impersonator_id,
            "sub": partner_user_id,
            "jti": jti,
        },
        ttl_seconds=ttl_seconds,
    )


def decode_and_consume_return_token(token: str) -> dict[str, Any]:
    payload = decode_token(token)
    if payload.get("typ") != RETURN_TOKEN_TYP:
        raise ValueError("Invalid return token type")
    jti = payload.get("jti")
    if not jti or not isinstance(jti, str):
        raise ValueError("Invalid return token")
    impersonator_id = payload.get("imp")
    partner_user_id = payload.get("sub")
    if not impersonator_id or not partner_user_id:
        raise ValueError("Invalid return token")
    _consume_return_jti(jti, float(payload["exp"]))
    return payload
