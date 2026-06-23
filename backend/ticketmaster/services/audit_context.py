from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

SMOKE_CHECK_HEADER = "x-ticketmaster-smoke"
SMOKE_CHECK_HEADER_VALUE = "1"
SMOKE_REQUEST_HEADERS = {SMOKE_CHECK_HEADER: SMOKE_CHECK_HEADER_VALUE}

_audit_suppressed: ContextVar[bool] = ContextVar("audit_suppressed", default=False)


def is_audit_suppressed() -> bool:
    return _audit_suppressed.get()


def request_is_smoke_check(request) -> bool:
    return request.headers.get(SMOKE_CHECK_HEADER, "").strip() == SMOKE_CHECK_HEADER_VALUE


@contextmanager
def suppress_audit() -> Iterator[None]:
    token = _audit_suppressed.set(True)
    try:
        yield
    finally:
        _audit_suppressed.reset(token)
