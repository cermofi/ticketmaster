from __future__ import annotations

import pytest

from ticketmaster.services import admin, tickets
from ticketmaster.services.errors import PermissionDenied, ValidationError
from ticketmaster.services.internal_roles import get_internal_roles


def test_single_role_user_backward_compatibility(db, fixture_data):
    assert get_internal_roles(fixture_data["l1"]) == ["L1"]
    assert fixture_data["l1"].internal_role == "L1"
    assert tickets.can_view_ticket(db, fixture_data["l1"], _l1_ticket(db, fixture_data))


def test_create_internal_user_with_multiple_roles(db, fixture_data):
    user = admin.create_internal_user(
        db,
        email="multi@example.test",
        name="Multi Role",
        roles=["L1", "L2"],
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()

    assert get_internal_roles(user) == ["L1", "L2"]
    assert user.internal_role == "L1"


def test_update_internal_user_roles(db, fixture_data):
    admin.update_user(
        db,
        user_id=fixture_data["l1"].id,
        roles=["L1", "L3"],
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()

    assert get_internal_roles(fixture_data["l1"]) == ["L1", "L3"]


def test_multi_role_user_gets_union_of_permissions(db, fixture_data):
    multi = admin.create_internal_user(
        db,
        email="l1-l2@example.test",
        name="L1 and L2",
        roles=["L1", "L2"],
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()

    l1_ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["dm"],
        ticket_type="Operational Request",
        priority="Normal",
        title="L1 queue",
        description="Visible to L1",
        team="L1",
        source="test",
    )
    l2_ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["dm"],
        ticket_type="Operational Request",
        priority="Normal",
        title="L2 queue",
        description="Visible to L2",
        team="L2",
        source="test",
    )
    db.commit()

    assert tickets.can_view_ticket(db, multi, l1_ticket)
    assert tickets.can_view_ticket(db, multi, l2_ticket)
    visible_ids = {ticket.id for ticket in tickets.list_visible_tickets(db, actor=multi)}
    assert l1_ticket.id in visible_ids
    assert l2_ticket.id in visible_ids


def test_multi_role_resolver_can_act_on_either_team_ticket(db, fixture_data):
    multi = admin.create_internal_user(
        db,
        email="resolver-multi@example.test",
        name="Resolver Multi",
        roles=["L1", "L2"],
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()

    ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Needs L2",
        description="Assign to L2",
        client_id=fixture_data["client_a"].id,
        source="test",
    )
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", assignee_ref=multi.email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=multi, new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=multi, new_status="Resolved", source="test")

    assert ticket.status == "Resolved"


def test_assignee_must_have_matching_resolver_role(db, fixture_data):
    multi = admin.create_internal_user(
        db,
        email="l1-only-assign@example.test",
        name="L1 only assignee",
        roles=["L1", "L2"],
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()
    l1_ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Assign L1",
        description="Allowed",
        client_id=fixture_data["client_a"].id,
        source="test",
    )
    l3_ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Assign L3",
        description="Should fail",
        client_id=fixture_data["client_a"].id,
        source="test",
    )

    tickets.assign_ticket(db, ticket=l1_ticket, actor=fixture_data["dm"], team="L1", assignee_ref=multi.email, source="test")

    with pytest.raises(ValidationError):
        tickets.assign_ticket(db, ticket=l3_ticket, actor=fixture_data["dm"], team="L3", assignee_ref=multi.email, source="test")


def test_internal_user_roles_validation(db, fixture_data):
    with pytest.raises(ValidationError, match="at most 3 roles"):
        admin.create_internal_user(
            db,
            email="too-many@example.test",
            name="Too Many",
            roles=["L1", "L2", "L3", "Admin"],
            actor=fixture_data["admin"],
            source="test",
        )

    with pytest.raises(ValidationError, match="At least one internal role"):
        admin.create_internal_user(
            db,
            email="none@example.test",
            name="No Roles",
            roles=[],
            actor=fixture_data["admin"],
            source="test",
        )


def test_update_user_with_legacy_single_role_field(db, fixture_data):
    admin.update_user(db, user_id=fixture_data["l2"].id, role="L3", actor=fixture_data["admin"], source="test")
    db.commit()

    assert get_internal_roles(fixture_data["l2"]) == ["L3"]
    assert fixture_data["l2"].internal_role == "L3"


def test_delivery_manager_with_extra_team_keeps_admin_permissions(db, fixture_data):
    admin.update_user(
        db,
        user_id=fixture_data["dm"].id,
        roles=["DeliveryManager", "L1"],
        actor=fixture_data["admin"],
        source="test",
    )
    db.commit()

    ticket = tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="DM still manages",
        description="On behalf allowed",
        client_id=fixture_data["client_a"].id,
        source="test",
    )
    on_behalf = tickets.create_partner_ticket_on_behalf(
        db,
        actor=fixture_data["dm"],
        partner_id=fixture_data["partner_a"].id,
        owner_ref=fixture_data["responsible_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="Created by DM multi-role",
        description="Still allowed",
        client_id=fixture_data["client_a"].id,
        source="test",
    )

    tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["dm"], ticket_type="Integration", source="test")
    assert on_behalf.id
    assert ticket.type == "Integration"


def _l1_ticket(db, fixture_data):
    ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["dm"],
        ticket_type="Operational Request",
        priority="Normal",
        title="L1 only",
        description="For visibility test",
        team="L1",
        source="test",
    )
    db.commit()
    return ticket
