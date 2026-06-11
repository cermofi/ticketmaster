from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import Client, Partner, Ticket, User
from ticketmaster.services import admin, tickets


def seed_dev(db: Session) -> dict:
    created: dict[str, list[str]] = {"users": [], "partners": [], "clients": [], "tickets": []}

    if not db.scalar(select(User).where(User.email == "admin@example.test")):
        for email, name, role in [
            ("admin@example.test", "Admin User", "Admin"),
            ("dm@example.test", "Delivery Manager", "DeliveryManager"),
            ("l1@example.test", "L1 Service Desk", "L1"),
            ("l2@example.test", "L2 Application Support", "L2"),
            ("l3@example.test", "L3 Development", "L3"),
        ]:
            user = admin.create_internal_user(db, email=email, name=name, role=role, source="cli")
            created["users"].append(user.email)

    partner = db.scalar(select(Partner).where(Partner.key.in_(["acme-partner", "acme"])).order_by(Partner.created_at.asc()))
    if not partner:
        partner = admin.create_partner(db, name="Acme Partner", source="cli")
        created["partners"].append(partner.key)

    client = db.scalar(select(Client).where(Client.key.in_(["acme-partner-acme-bank", "acme-bank"])).order_by(Client.created_at.asc()))
    if not client:
        client = admin.create_client(db, partner_key_or_id=partner.id, name="Acme Bank", source="cli")
        created["clients"].append(client.key)

    responsible = db.scalar(select(User).where(User.email == "responsible@acme.example"))
    if not responsible:
        responsible = admin.invite_partner_user(
            db,
            partner_key_or_id=partner.id,
            email="responsible@acme.example",
            name="Responsible Partner User",
            role="responsible",
            source="cli",
        )
        created["users"].append(responsible.email)

    technical = db.scalar(select(User).where(User.email == "technical@acme.example"))
    if not technical:
        technical = admin.invite_partner_user(
            db,
            partner_key_or_id=partner.id,
            email="technical@acme.example",
            name="Technical Partner User",
            role="technical",
            source="cli",
        )
        created["users"].append(technical.email)

    admin.assign_responsible_to_client(db, client_key_or_id=client.id, user_email_or_id=responsible.id, source="cli")

    if not db.scalar(select(Ticket).where(Ticket.title == "Seeded partner question")):
        ticket = tickets.create_partner_ticket(
            db,
            actor=responsible,
            ticket_type="Question",
            priority="Normal",
            title="Seeded partner question",
            description="This ticket is created by seed-dev for local smoke tests.",
            client_id=client.id,
            participant_ids=[technical.id],
            source="cli",
        )
        created["tickets"].append(ticket.id)

    if not db.scalar(select(Ticket).where(Ticket.title == "Seeded system integration ticket")):
        ticket = tickets.create_system_ticket(
            db,
            partner_id=partner.id,
            ticket_type="Operational Request",
            priority="Normal",
            title="Seeded system integration ticket",
            description="This system ticket is created by seed-dev for API smoke tests.",
            team="L1",
            source="cli",
        )
        created["tickets"].append(ticket.id)

    db.commit()
    return {**created, "dev_partner_password": settings.dev_password}
