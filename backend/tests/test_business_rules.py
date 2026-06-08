from __future__ import annotations

import pytest
from sqlalchemy import select

from ticketmaster.core.security import hash_password
from ticketmaster.models import CommentRevision, GitLabLink, Ticket
from ticketmaster.services import auth
from ticketmaster.services import admin, tickets
from ticketmaster.services.errors import ConflictError, PermissionDenied, ValidationError


def create_partner_ticket(db, data):
    ticket = tickets.create_partner_ticket(
        db,
        actor=data["responsible_a"],
        ticket_type="Question",
        priority="Normal",
        title="Question for support",
        description="Need help",
        client_id=data["client_a"].id,
        participant_ids=[],
        source="test",
    )
    db.commit()
    return ticket


def test_partner_isolation(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    assert tickets.can_view_ticket(db, fixture_data["responsible_a"], ticket)
    assert not tickets.can_view_ticket(db, fixture_data["responsible_b"], ticket)


def test_visible_tickets_are_paginated(db, fixture_data):
    for index in range(3):
        tickets.create_partner_ticket(
            db,
            actor=fixture_data["responsible_a"],
            ticket_type="Question",
            priority="Normal",
            title=f"Question {index}",
            description="Need help",
            client_id=fixture_data["client_a"].id,
            source="test",
        )
    db.commit()

    rows, total = tickets.list_visible_tickets_page(db, actor=fixture_data["responsible_a"], limit=2, offset=0)

    assert total == 3
    assert len(rows) == 2


def test_technical_user_cannot_create_ticket(db, fixture_data):
    with pytest.raises(PermissionDenied):
        tickets.create_partner_ticket(
            db,
            actor=fixture_data["technical_a"],
            ticket_type="Question",
            priority="Normal",
            title="Not allowed",
            description="Technical contact cannot create",
        )


def test_inactive_users_cannot_create_tickets_or_comments_and_cannot_log_in(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    partner_user = fixture_data["responsible_a"]
    partner_user.password_hash = hash_password("SecretPass123")
    partner_user.active = False

    internal_user = fixture_data["l1"]
    internal_user.active = False

    with pytest.raises(PermissionDenied, match="Account is inactive"):
        tickets.create_partner_ticket(
            db,
            actor=partner_user,
            ticket_type="Question",
            priority="Normal",
            title="Inactive partner",
            description="Should not be accepted",
            client_id=fixture_data["client_a"].id,
            source="test",
        )

    tickets.add_participant(db, ticket=ticket, actor=fixture_data["responsible_a"], user_id=fixture_data["technical_a"].id, source="test")
    with pytest.raises(PermissionDenied, match="Account is inactive"):
        tickets.add_comment(db, ticket=ticket, actor=partner_user, body="Nope")
    with pytest.raises(PermissionDenied, match="Account is inactive"):
        tickets.add_internal_note(db, ticket=ticket, actor=internal_user, body="Nope")

    with pytest.raises(PermissionDenied, match="Account is inactive"):
        tickets.create_internal_ticket(
            db,
            actor=internal_user,
            ticket_type="Question",
            priority="Normal",
            title="Inactive internal",
            description="Should not be accepted",
            team="L1",
            source="test",
        )

    with pytest.raises(PermissionDenied, match="Account is inactive"):
        auth.authenticate_email_password(db, partner_user.email, "SecretPass123")

    with pytest.raises(PermissionDenied, match="Account is inactive"):
        auth.authenticate_dev_sso(db, internal_user.email)


def test_commenting_requires_participant(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(PermissionDenied):
        tickets.add_comment(db, ticket=ticket, actor=fixture_data["technical_a"], body="I am not in communication")

    tickets.add_participant(db, ticket=ticket, actor=fixture_data["responsible_a"], user_id=fixture_data["technical_a"].id, source="test")
    comment = tickets.add_comment(db, ticket=ticket, actor=fixture_data["technical_a"], body="Now I can comment")
    assert comment.body == "Now I can comment"


def test_ticket_owner_can_remove_non_owner_participant(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    technical = fixture_data["technical_a"]
    tickets.add_participant(db, ticket=ticket, actor=fixture_data["responsible_a"], user_id=technical.id, source="test")

    tickets.remove_participant(db, ticket=ticket, actor=fixture_data["responsible_a"], user_id=technical.id, source="test")

    with pytest.raises(PermissionDenied):
        tickets.add_comment(db, ticket=ticket, actor=technical, body="Removed participant")


def test_ticket_owner_cannot_be_removed_from_participants(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(ValidationError):
        tickets.remove_participant(db, ticket=ticket, actor=fixture_data["responsible_a"], user_id=fixture_data["responsible_a"].id, source="test")


def test_transfer_owner_requires_same_partner_and_client_assignment(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(ValidationError):
        tickets.transfer_owner(db, ticket=ticket, actor=fixture_data["responsible_a"], new_owner_ref=fixture_data["responsible_b"].email, source="test")


def test_partner_deactivation_cleans_up_clients_users_and_detaches_tickets(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    ticket_id = ticket.id

    partner = admin.deactivate_partner(db, partner_id=fixture_data["partner_a"].id, actor=fixture_data["admin"], source="test")

    assert partner.active is False
    assert fixture_data["client_a"].active is False
    assert fixture_data["responsible_a"].active is False
    assert fixture_data["technical_a"].active is False

    detached_ticket = db.get(Ticket, ticket_id)
    assert detached_ticket is not None
    assert detached_ticket.partner_id is None
    assert detached_ticket.client_id is None


def test_tickets_survive_other_entity_deactivations(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    ticket_id = ticket.id

    with pytest.raises(ValidationError):
        admin.deactivate_client(db, client_id=fixture_data["client_a"].id, actor=fixture_data["admin"], source="test")

    assignment = admin.list_client_assignments(db, client_id=fixture_data["client_a"].id)[0]
    admin.remove_client_assignment(db, assignment_id=assignment.id, actor=fixture_data["admin"], source="test")
    admin.deactivate_client(db, client_id=fixture_data["client_a"].id, actor=fixture_data["admin"], source="test")
    admin.deactivate_user_by_id(db, user_id=fixture_data["technical_a"].id, actor=fixture_data["admin"], source="test")

    assert db.get(Ticket, ticket_id) is not None
    assert db.scalar(select(Ticket).where(Ticket.id == ticket_id)) is not None


def test_workflow_transition_matrix(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Resolved", source="test")

    with pytest.raises(ValidationError):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")


def test_closed_ticket_cannot_be_assigned(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Resolved", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Closed", source="test")

    with pytest.raises(ValidationError):
        tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", source="test")


def test_delivery_manager_can_return_assigned_ticket_to_queue(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")

    tickets.unassign_ticket(db, ticket=ticket, actor=fixture_data["dm"], source="test")

    assert ticket.status == "Assigned"
    assert ticket.resolver_team == "L1"
    assert ticket.assignee_id is None


def test_resolver_cannot_return_ticket_to_queue(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")

    with pytest.raises(PermissionDenied):
        tickets.unassign_ticket(db, ticket=ticket, actor=fixture_data["l1"], source="test")


def test_assigned_ticket_cannot_change_resolver_team(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")

    with pytest.raises(ValidationError):
        tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", source="test")

    assert ticket.resolver_team == "L1"


def test_assigned_ticket_can_change_assignee_within_resolver_team(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")

    assert ticket.resolver_team == "L1"
    assert ticket.assignee_id == fixture_data["l1"].id


def test_l3_in_progress_requires_gitlab_issue(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", source="test")
    link = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id))
    if link:
        db.delete(link)
        db.flush()

    with pytest.raises(ConflictError):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")


def test_internal_ticket_not_visible_to_partner(db, fixture_data):
    ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["dm"],
        ticket_type="Operational Request",
        priority="Normal",
        title="Internal task",
        description="Internal only",
        team="L1",
        source="test",
    )
    assert ticket.internal
    assert not tickets.can_view_ticket(db, fixture_data["responsible_a"], ticket)
    assert tickets.can_view_ticket(db, fixture_data["l1"], ticket)


def test_internal_ticket_creator_is_owner_and_can_view_it(db, fixture_data):
    ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["l2"],
        ticket_type="Operational Request",
        priority="Normal",
        title="L2-owned internal task",
        description="Owner visibility",
        team="L1",
        source="test",
    )

    assert ticket.owner_id == fixture_data["l2"].id
    assert tickets.can_view_ticket(db, fixture_data["l2"], ticket)
    assert ticket in tickets.list_visible_tickets(db, actor=fixture_data["l2"])


def test_ticket_model_has_no_delete_flag(db, fixture_data):
    create_partner_ticket(db, fixture_data)
    assert db.scalar(select(Ticket)).status == "New"
    assert not hasattr(tickets, "delete_ticket")


def test_comment_edit_and_soft_delete_is_admin_dm_only(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    comment = tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="Original")

    with pytest.raises(PermissionDenied):
        tickets.edit_comment(db, comment=comment, actor=fixture_data["responsible_a"], body="Partner edit", source="test")

    tickets.edit_comment(db, comment=comment, actor=fixture_data["dm"], body="Edited", source="test")
    assert comment.body == "Edited"
    assert db.scalar(select(CommentRevision).where(CommentRevision.comment_id == comment.id, CommentRevision.action == "edit"))

    tickets.soft_delete_comment(db, comment=comment, actor=fixture_data["admin"], source="test")
    assert comment.deleted_at is not None
    assert db.scalar(select(CommentRevision).where(CommentRevision.comment_id == comment.id, CommentRevision.action == "delete"))


def test_client_update_and_deactivation_blocks_new_usage(db, fixture_data):
    client = fixture_data["client_a"]

    admin.update_client(db, client_id=client.id, name="Renamed Client", actor=fixture_data["dm"], source="test")
    assert client.name == "Renamed Client"

    admin.deactivate_client(db, client_id=client.id, actor=fixture_data["dm"], source="test")
    assert client.active is False

    with pytest.raises(ValidationError):
        admin.assign_responsible_to_client(
            db,
            client_key_or_id=client.id,
            user_email_or_id=fixture_data["responsible_a"].id,
            actor=fixture_data["dm"],
            source="test",
        )

    with pytest.raises(ValidationError):
        tickets.create_partner_ticket(
            db,
            actor=fixture_data["responsible_a"],
            ticket_type="Question",
            priority="Normal",
            title="Inactive client",
            description="Should not be accepted",
            client_id=client.id,
            source="test",
        )


def test_partner_user_update_deactivate_and_reactivate(db, fixture_data):
    user = fixture_data["technical_a"]

    admin.update_user(
        db,
        user_id=user.id,
        email="technical-renamed@example.test",
        name="Technical Renamed",
        role="responsible",
        active=False,
        actor=fixture_data["dm"],
        source="test",
    )
    assert user.email == "technical-renamed@example.test"
    assert user.name == "Technical Renamed"
    assert user.partner_role == "responsible"
    assert user.active is False
    assert user.invitation_token is None

    admin.update_user(db, user_id=user.id, active=True, actor=fixture_data["dm"], source="test")
    assert user.active is True

    admin.deactivate_user_by_id(db, user_id=user.id, actor=fixture_data["dm"], source="test")
    assert user.active is False


def test_internal_user_updates_require_admin_and_keep_last_admin(db, fixture_data):
    with pytest.raises(PermissionDenied):
        admin.update_user(db, user_id=fixture_data["l1"].id, name="New L1", actor=fixture_data["dm"], source="test")

    with pytest.raises(ValidationError):
        admin.update_user(db, user_id=fixture_data["admin"].id, role="L1", actor=fixture_data["admin"], source="test")

    with pytest.raises(ValidationError):
        admin.deactivate_user_by_id(db, user_id=fixture_data["admin"].id, actor=fixture_data["admin"], source="test")
