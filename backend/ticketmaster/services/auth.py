from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.core.security import create_token, hash_password, verify_password
from ticketmaster.models import User
from ticketmaster.services.errors import PermissionDenied, ValidationError


def authenticate_email_password(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if not user or user.kind != "partner":
        raise PermissionDenied("Invalid e-mail or password")
    if not user.active:
        raise PermissionDenied("Account is inactive")
    if not verify_password(password, user.password_hash):
        raise PermissionDenied("Invalid e-mail or password")
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
