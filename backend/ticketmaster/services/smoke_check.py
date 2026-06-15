from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ticketmaster.core.config import settings


def _request(method: str, url: str, *, headers: dict[str, str] | None = None, body: dict | None = None, timeout: float = 15.0) -> tuple[int, Any]:
    data = None
    req_headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)
    request = Request(url, data=data, headers=req_headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
        try:
            parsed: Any = json.loads(payload) if payload else None
        except json.JSONDecodeError:
            parsed = payload
        return response.status, parsed


def _record(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any) -> None:
    checks.append({"name": name, "ok": ok, "detail": detail})


def run_smoke_check(
    *,
    base_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    root = (base_url or os.getenv("SMOKE_CHECK_BASE_URL") or settings.base_url).rstrip("/")
    login_email = email or os.getenv("SMOKE_CHECK_EMAIL")
    login_password = password or os.getenv("SMOKE_CHECK_PASSWORD")
    checks: list[dict[str, Any]] = []
    token: str | None = None

    for name, path in [
        ("health", "/api/health"),
        ("ready", "/api/ready"),
        ("meta", "/api/meta"),
    ]:
        try:
            status, payload = _request("GET", f"{root}{path}")
            _record(checks, name, status == 200 and isinstance(payload, dict), {"status": status, "body": payload})
        except (HTTPError, URLError, TimeoutError) as exc:
            _record(checks, name, False, {"error": str(exc)})

    if login_email and login_password:
        try:
            status, payload = _request(
                "POST",
                f"{root}/api/auth/login",
                body={"email": login_email, "password": login_password},
            )
            ok = status == 200 and isinstance(payload, dict) and bool(payload.get("access_token"))
            token = payload.get("access_token") if isinstance(payload, dict) else None
            _record(checks, "auth.login", ok, {"status": status, "authenticated": ok})
        except (HTTPError, URLError, TimeoutError) as exc:
            _record(checks, "auth.login", False, {"error": str(exc)})
    else:
        _record(checks, "auth.login", True, {"skipped": True, "reason": "SMOKE_CHECK_EMAIL/PASSWORD not set"})

    if token:
        auth_headers = {"Authorization": f"Bearer {token}"}
        for name, path in [
            ("auth.me", "/api/auth/me"),
            ("tickets.export", "/api/tickets/export?format=json&limit=1"),
        ]:
            try:
                status, payload = _request("GET", f"{root}{path}", headers=auth_headers)
                _record(checks, name, status == 200, {"status": status, "has_body": payload is not None})
            except (HTTPError, URLError, TimeoutError) as exc:
                _record(checks, name, False, {"error": str(exc)})
    else:
        _record(checks, "auth.me", True, {"skipped": True, "reason": "no auth token"})
        _record(checks, "tickets.export", True, {"skipped": True, "reason": "no auth token"})

    passed = all(row["ok"] for row in checks)
    return {
        "status": "ok" if passed else "failed",
        "base_url": root,
        "read_only": True,
        "checks": checks,
    }
