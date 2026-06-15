from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ticketmaster.core.security import create_token, hash_password, verify_password
from ticketmaster.models import User
from ticketmaster.services.errors import PermissionDenied, ValidationError

_INVALID_CREDENTIALS = "Invalid e-mail or password"
_AMBIGUOUS_NAME = "Multiple accounts match this login name; use e-mail instead"


def _resolve_user_by_identifier(db: Session, identifier: str) -> User | None:
    normalized = identifier.strip()
    if not normalized:
        return None
    if "@" in normalized:
        return db.scalar(select(User).where(User.email == normalized.lower()))
    matches = db.scalars(select(User).where(func.lower(User.name) == normalized.lower())).all()
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise PermissionDenied(_AMBIGUOUS_NAME)
    return None


def authenticate_email_password(db: Session, email: str, password: str) -> tuple[User, str]:
    try:
        user = _resolve_user_by_identifier(db, email)
    except PermissionDenied:
        raise
    if not user:
        raise PermissionDenied(_INVALID_CREDENTIALS)
    if not user.active:
        raise PermissionDenied("Account is inactive")
    if not user.password_hash:
        raise PermissionDenied(_INVALID_CREDENTIALS)
    if not verify_password(password, user.password_hash):
        raise PermissionDenied(_INVALID_CREDENTIALS)
    return user, create_token({"sub": user.id})


def authenticate_dev_sso(db: Session, email: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or user.kind != "internal":
        raise PermissionDenied("Internal user is not provisioned or is inactive")
    if not user.active:
        raise PermissionDenied("Account is inactive")
    return user, create_token({"sub": user.id, "sso": "dev"})


def activate_invitation(db: Session, token: str, password: str) -> tuple[User, str]:
    if len(password) < 8:
        raise ValidationError("Password must contain at least 8 characters")
    user = db.scalar(select(User).where(User.invitation_token == token))
    if not user:
        raise PermissionDenied("Invitation token is invalid")
    if not user.active:
        raise PermissionDenied("Account is inactive")
    user.password_hash = hash_password(password)
    user.invitation_token = None
    db.flush()
    return user, create_token({"sub": user.id})
