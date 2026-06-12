from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ticketmaster.core.security import hash_password, verify_password
from ticketmaster.models import User
from ticketmaster.services.audit import audit
from ticketmaster.services.errors import PermissionDenied, ValidationError

_PASSWORD_MIN_LENGTH = 8
_LETTER_RE = re.compile(r"[A-Za-z]")
_NUMBER_RE = re.compile(r"\d")
_EMAIL_READONLY_REASON = "E-mail is used as login identity and cannot be changed here."


def profile_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "kind": user.kind,
        "internal_role": user.internal_role,
        "partner_id": user.partner_id,
        "partner_role": user.partner_role,
        "active": user.active,
        "created_at": user.created_at,
        "email_editable": False,
        "email_readonly_reason": _EMAIL_READONLY_REASON,
    }


def update_own_profile(
    db: Session,
    *,
    user: User,
    name: str | None = None,
    email: str | None = None,
    source: str = "ui",
) -> User:
    old = {"name": user.name}
    if name is not None:
        cleaned_name = _clean_name(name)
        user.name = cleaned_name
    if email is not None:
        cleaned_email = email.strip().lower()
        if cleaned_email != user.email:
            raise ValidationError(_EMAIL_READONLY_REASON)
    db.flush()
    new = {"name": user.name}
    if old != new:
        audit(
            db,
            entity_type="User",
            entity_id=user.id,
            action="account.update",
            actor=user,
            source=source,
            old_value=old,
            new_value=new,
        )
    return user


def change_own_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    confirm_password: str,
    source: str = "ui",
) -> None:
    if not user.password_hash:
        raise ValidationError("Password change is not available for this account")
    if not verify_password(current_password, user.password_hash):
        raise PermissionDenied("Current password is invalid")
    if new_password != confirm_password:
        raise ValidationError("New password and confirmation do not match")
    _validate_password_policy(new_password)
    if verify_password(new_password, user.password_hash):
        raise ValidationError("New password must be different from current password")
    user.password_hash = hash_password(new_password)
    user.invitation_token = None
    db.flush()
    audit(
        db,
        entity_type="User",
        entity_id=user.id,
        action="account.password_change",
        actor=user,
        source=source,
        new_value={"password_changed": True},
    )


def _clean_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Name is required")
    return cleaned


def _validate_password_policy(password: str) -> None:
    if len(password) < _PASSWORD_MIN_LENGTH:
        raise ValidationError("Password must contain at least 8 characters")
    if not _LETTER_RE.search(password):
        raise ValidationError("Password must contain at least one letter")
    if not _NUMBER_RE.search(password):
        raise ValidationError("Password must contain at least one number")
