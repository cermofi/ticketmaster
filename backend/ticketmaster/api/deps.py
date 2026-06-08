from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from ticketmaster.core.database import get_db
from ticketmaster.core.security import decode_token
from ticketmaster.models import User
from ticketmaster.services.errors import PermissionDenied


DbSession = Annotated[Session, Depends(get_db)]


def current_user(db: DbSession, authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise PermissionDenied("Bearer token is required")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise PermissionDenied(str(exc)) from exc
    user = db.get(User, payload.get("sub"))
    if not user or not user.active:
        raise PermissionDenied("Authenticated user is inactive or missing")
    return user


CurrentUser = Annotated[User, Depends(current_user)]
