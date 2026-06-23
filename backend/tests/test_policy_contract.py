from __future__ import annotations

import pytest

from ticketmaster.models import Ticket
from ticketmaster.models.entities import new_id
from ticketmaster.policy import evaluate_visibility, get_action_rule, load_access_matrix
from ticketmaster.services import admin, tickets
from ticketmaster.services.errors import PermissionDenied
from ticketmaster.services.internal_roles import set_internal_roles


def _resolve_actor(db, fixture_data, spec: dict):
    if spec.get("kind") == "partner":
        partner = fixture_data[spec["partner_key"]]
        role = spec.get("role", "responsible")
        if role == "responsible":
            return fixture_data[f"responsible_{partner.name.split()[-1].lower()}"]
        raise ValueError(f"Unsupported partner role fixture: {role}")
    roles = spec.get("roles")
    if roles is None:
        raise ValueError("internal actor requires roles")
    if not roles:
        if "no_resolver" in fixture_data:
            return fixture_data["no_resolver"]
        user = admin.create_internal_user(
            db,
            email="no-resolver@example.test",
            name="No Resolver",
            role="Admin",
            source="test",
        )
        set_internal_roles(user, ["Admin"])
        user.internal_roles = []
        user.internal_role = None
        db.flush()
        return user
    key_map = {
        "Admin": "admin",
        "DeliveryManager": "dm",
        "L1": "l1",
        "L2": "l2",
        "L3": "l3",
    }
    primary = roles[0]
    return fixture_data[key_map[primary]]


def _build_ticket(db, fixture_data, spec: dict) -> Ticket:
    ticket_class = spec.get("class", "partner")
    partner = fixture_data[spec.get("partner_key", "partner_a")]
    if ticket_class == "internal":
        ticket = Ticket(
            id=new_id(),
            partner_id=None,
            client_id=None,
            owner_id=fixture_data.get(spec.get("owner_key", "dm")).id if spec.get("owner_key") else fixture_data["dm"].id,
            created_by_id=fixture_data[spec["created_by_key"]].id if spec.get("created_by_key") else fixture_data["dm"].id,
            internal=True,
            system=False,
            type="Operational Request",
            priority="Normal",
            status=spec.get("status", "New"),
            resolver_team=spec.get("resolver_team"),
            assignee_id=fixture_data[spec["assignee_key"]].id if spec.get("assignee_key") else None,
            title="Policy contract ticket",
            description="Contract test",
        )
    elif ticket_class == "system":
        ticket = Ticket(
            id=new_id(),
            partner_id=partner.id,
            client_id=None,
            owner_id=None,
            created_by_id=None,
            internal=False,
            system=True,
            type="Operational Request",
            priority="Normal",
            status=spec.get("status", "New"),
            resolver_team=spec.get("resolver_team"),
            assignee_id=None,
            title="System ticket",
            description="Contract test",
        )
    else:
        ticket = Ticket(
            id=new_id(),
            partner_id=partner.id,
            client_id=fixture_data["client_a"].id if partner.id == fixture_data["partner_a"].id else None,
            owner_id=fixture_data["responsible_a"].id if partner.id == fixture_data["partner_a"].id else fixture_data["responsible_b"].id,
            created_by_id=fixture_data[spec["created_by_key"]].id if spec.get("created_by_key") else fixture_data["responsible_a"].id,
            internal=False,
            system=False,
            type="Question",
            priority="Normal",
            status=spec.get("status", "New"),
            resolver_team=spec.get("resolver_team"),
            assignee_id=fixture_data[spec["assignee_key"]].id if spec.get("assignee_key") else None,
            title="Partner ticket",
            description="Contract test",
        )
    db.add(ticket)
    db.flush()
    return ticket


@pytest.fixture()
def no_resolver_internal(db):
    user = admin.create_internal_user(
        db,
        email="no-resolver@example.test",
        name="No Resolver",
        role="Admin",
        source="test",
    )
    user.internal_roles = []
    user.internal_role = None
    db.flush()
    return user


def test_access_matrix_loads(db):
    matrix = load_access_matrix()
    assert matrix["version"] == 1
    assert len(matrix["visibility_scenarios"]) >= 10


@pytest.mark.parametrize("scenario", load_access_matrix()["visibility_scenarios"], ids=lambda row: row["name"])
def test_visibility_contract(db, fixture_data, no_resolver_internal, scenario):
    fixture_data["no_resolver"] = no_resolver_internal
    actor = _resolve_actor(db, fixture_data, scenario["actor"])
    ticket = _build_ticket(db, fixture_data, scenario["ticket"])
    expected = scenario["visible"]
    assert evaluate_visibility(actor, ticket) is expected
    assert tickets.can_view_ticket(db, actor, ticket) is expected


def test_internal_to_partner_create_intent_contract(db, fixture_data):
    rule = get_action_rule("create_partner_on_behalf")
    assert rule is not None
    intent = rule["intent"]
    assert intent["status"] == "Assigned"
    assert intent["assignee"] == "creator"

    ticket = tickets.create_partner_ticket_on_behalf(
        db,
        actor=fixture_data["l1"],
        partner_id=fixture_data["partner_a"].id,
        owner_ref=fixture_data["responsible_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="Policy intent",
        description="Contract",
        client_id=fixture_data["client_a"].id,
        source="test",
    )
    assert ticket.status == intent["status"]
    assert ticket.assignee_id == fixture_data["l1"].id


def test_delete_ticket_action_contract(db, fixture_data):
    rule = get_action_rule("delete_ticket")
    assert rule["allowed_actor_roles"] == ["Admin"]

    ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Delete me",
        description="x",
        client_id=fixture_data["client_a"].id,
        source="test",
    )
    db.commit()

    with pytest.raises(PermissionDenied):
        tickets.delete_ticket(db, ticket=ticket, actor=fixture_data["dm"], source="test")

    tickets.delete_ticket(db, ticket=ticket, actor=fixture_data["admin"], source="test")
