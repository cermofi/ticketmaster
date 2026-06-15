from __future__ import annotations

import pytest

from ticketmaster.core.config import settings
from ticketmaster.core.security import hash_password, verify_password
from ticketmaster.services import admin, auth
from ticketmaster.services.errors import PermissionDenied


def test_partner_login_by_email(db, fixture_data):
    user, token = auth.authenticate_email_password(
        db,
        fixture_data["responsible_a"].email,
        settings.dev_password,
    )
    assert user.id == fixture_data["responsible_a"].id
    assert token


def test_internal_login_by_email_when_password_set(db, fixture_data):
    admin.ensure_dev_login_password(fixture_data["admin"])
    db.commit()

    user, token = auth.authenticate_email_password(
        db,
        fixture_data["admin"].email,
        settings.dev_password,
    )
    assert user.id == fixture_data["admin"].id
    assert token


def test_login_by_unique_name(db, fixture_data):
    admin.ensure_dev_login_password(fixture_data["l1"])
    db.commit()

    user, _token = auth.authenticate_email_password(db, fixture_data["l1"].name, settings.dev_password)
    assert user.id == fixture_data["l1"].id


def test_login_by_ambiguous_name_returns_clear_error(db, fixture_data):
    fixture_data["l1"].name = "Shared Name"
    fixture_data["l2"].name = "Shared Name"
    admin.ensure_dev_login_password(fixture_data["l1"])
    admin.ensure_dev_login_password(fixture_data["l2"])
    db.commit()

    with pytest.raises(PermissionDenied, match="Multiple accounts match this login name"):
        auth.authenticate_email_password(db, "Shared Name", settings.dev_password)


def test_login_rejects_wrong_password(db, fixture_data):
    with pytest.raises(PermissionDenied, match="Invalid e-mail or password"):
        auth.authenticate_email_password(db, fixture_data["responsible_a"].email, "WrongPassword123")


def test_login_rejects_internal_user_without_password(db, fixture_data):
    with pytest.raises(PermissionDenied, match="Invalid e-mail or password"):
        auth.authenticate_email_password(db, fixture_data["admin"].email, settings.dev_password)


def test_ensure_dev_login_password_sets_default_once(db, fixture_data):
    assert fixture_data["admin"].password_hash is None
    changed = admin.ensure_dev_login_password(fixture_data["admin"])
    assert changed is True
    assert verify_password(settings.dev_password, fixture_data["admin"].password_hash)

    changed_again = admin.ensure_dev_login_password(fixture_data["admin"])
    assert changed_again is False


def test_login_rejects_inactive_user(db, fixture_data):
    partner_user = fixture_data["responsible_a"]
    partner_user.password_hash = hash_password("SecretPass123")
    partner_user.active = False
    db.commit()

    with pytest.raises(PermissionDenied, match="Account is inactive"):
        auth.authenticate_email_password(db, partner_user.email, "SecretPass123")
