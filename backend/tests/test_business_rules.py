from __future__ import annotations

import pytest
from sqlalchemy import select

from ticketmaster.models import CommentRevision, GitLabLink, Ticket
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


def test_workflow_transition_matrix(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Resolved", source="test")

    with pytest.raises(ValidationError):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")


def test_l1_to_l2_and_l2_to_l3_escalation(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["l1"], team="L2", source="test")
    assert ticket.resolver_team == "L2"

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["l2"], team="L3", source="test")
    assert ticket.resolver_team == "L3"


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
