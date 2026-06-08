from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ticketmaster.models import Base
from ticketmaster.services import admin


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fixture_data(db):
    admin_user = admin.create_internal_user(db, email="admin@example.test", name="Admin", role="Admin", source="test")
    dm = admin.create_internal_user(db, email="dm@example.test", name="DM", role="DeliveryManager", source="test")
    l1 = admin.create_internal_user(db, email="l1@example.test", name="L1", role="L1", source="test")
    l2 = admin.create_internal_user(db, email="l2@example.test", name="L2", role="L2", source="test")
    l3 = admin.create_internal_user(db, email="l3@example.test", name="L3", role="L3", source="test")
    partner_a = admin.create_partner(db, name="Partner A", source="test")
    partner_b = admin.create_partner(db, name="Partner B", source="test")
    client_a = admin.create_client(db, partner_key_or_id=partner_a.id, name="Client A", source="test")
    responsible_a = admin.invite_partner_user(
        db,
        partner_key_or_id=partner_a.id,
        email="responsible-a@example.test",
        name="Responsible A",
        role="responsible",
        source="test",
    )
    technical_a = admin.invite_partner_user(
        db,
        partner_key_or_id=partner_a.id,
        email="technical-a@example.test",
        name="Technical A",
        role="technical",
        source="test",
    )
    responsible_b = admin.invite_partner_user(
        db,
        partner_key_or_id=partner_b.id,
        email="responsible-b@example.test",
        name="Responsible B",
        role="responsible",
        source="test",
    )
    admin.assign_responsible_to_client(db, client_key_or_id=client_a.id, user_email_or_id=responsible_a.id, source="test")
    db.commit()
    return {
        "admin": admin_user,
        "dm": dm,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "partner_a": partner_a,
        "partner_b": partner_b,
        "client_a": client_a,
        "responsible_a": responsible_a,
        "technical_a": technical_a,
        "responsible_b": responsible_b,
    }
