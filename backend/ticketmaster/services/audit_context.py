from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_audit_suppressed: ContextVar[bool] = ContextVar("audit_suppressed", default=False)


def is_audit_suppressed() -> bool:
    return _audit_suppressed.get()


@contextmanager
def suppress_audit() -> Iterator[None]:
    token = _audit_suppressed.set(True)
    try:
        yield
    finally:
        _audit_suppressed.reset(token)
