from __future__ import annotations

import re
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from ticketmaster.api.deps import current_user
from ticketmaster.api.main import app
from ticketmaster.core.database import get_db
from ticketmaster.core.security import hash_password
from ticketmaster.models import AuditLog, Client, GitLabLink, Notification, Partner, Ticket, TicketParticipant, TicketWatcher, User
from ticketmaster.models.entities import new_id
from ticketmaster.services import auth
from ticketmaster.services import admin, ticket_exports, tickets
from ticketmaster.services.errors import ConflictError, NotFoundError, PermissionDenied, ValidationError


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


def test_partner_and_client_deletion_is_disabled(db, fixture_data):
    with pytest.raises(ValidationError, match="Partners cannot be deleted"):
        admin.delete_partner(db, partner_id=fixture_data["partner_a"].id, actor=fixture_data["admin"], source="test")

    with pytest.raises(ValidationError, match="Clients cannot be deleted"):
        admin.delete_client(db, client_id=fixture_data["client_a"].id, actor=fixture_data["admin"], source="test")


def test_new_ticket_queue_assignment_sets_status_queued(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    assert ticket.status == "New"

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")

    assert ticket.status == "Queued"
    assert ticket.resolver_team == "L1"
    assert ticket.assignee_id is None


def test_queued_ticket_assignee_assignment_sets_status_assigned(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", source="test")
    assert ticket.status == "Queued"

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", assignee_ref=fixture_data["l2"].email, source="test")

    assert ticket.status == "Assigned"
    assert ticket.assignee_id == fixture_data["l2"].id


def test_new_ticket_queue_and_assignee_together_ends_assigned(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    assert ticket.status == "New"

    tickets.assign_ticket(
        db,
        ticket=ticket,
        actor=fixture_data["dm"],
        team="L3",
        assignee_ref=fixture_data["l3"].email,
        source="test",
    )

    assert ticket.status == "Assigned"
    assert ticket.resolver_team == "L3"
    assert ticket.assignee_id == fixture_data["l3"].id


def test_unrelated_status_transitions_remain_valid(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["dm"], new_status="Rejected", source="test")
    assert ticket.status == "Rejected"

    ticket2 = create_partner_ticket(db, fixture_data)
    tickets.transition_ticket(db, ticket=ticket2, actor=fixture_data["dm"], new_status="Need more info", source="test")
    assert ticket2.status == "Need more info"


def test_workflow_transition_matrix(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    assert ticket.status == "Queued"
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    assert ticket.status == "Assigned"
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Resolved", source="test")

    with pytest.raises(ValidationError):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")


def test_closed_ticket_cannot_be_assigned(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Resolved", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["dm"], new_status="Closed", source="test")

    with pytest.raises(ValidationError):
        tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", source="test")


def test_delivery_manager_can_return_assigned_ticket_to_queue(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")

    tickets.unassign_ticket(db, ticket=ticket, actor=fixture_data["dm"], source="test")

    assert ticket.status == "Queued"
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
    assert ticket.status == "Queued"

    with pytest.raises(ValidationError):
        tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L2", source="test")

    assert ticket.resolver_team == "L1"


def test_assigned_ticket_can_change_assignee_within_resolver_team(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    assert ticket.status == "Queued"

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")

    assert ticket.status == "Assigned"
    assert ticket.resolver_team == "L1"
    assert ticket.assignee_id == fixture_data["l1"].id


def test_admin_and_delivery_manager_can_change_ticket_type(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["dm"], ticket_type="Integration", source="test")
    assert ticket.type == "Integration"

    tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["admin"], ticket_type="Security Issue", source="test")
    assert ticket.type == "Security Issue"
    assert ticket.priority == "Critical"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "ticket.type_change", AuditLog.entity_id == ticket.id))


def test_non_admin_roles_cannot_change_ticket_type(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(PermissionDenied):
        tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["l1"], ticket_type="Integration", source="test")

    with pytest.raises(PermissionDenied):
        tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["responsible_a"], ticket_type="Integration", source="test")


def test_change_ticket_type_rejects_unknown_type(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(ValidationError):
        tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["dm"], ticket_type="Unsupported Type", source="test")


def test_admin_and_delivery_manager_can_change_ticket_priority(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["dm"], priority="High", source="test")
    assert ticket.priority == "High"

    tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["admin"], priority="Low", source="test")
    assert ticket.priority == "Low"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "ticket.priority_change", AuditLog.entity_id == ticket.id))


def test_non_admin_roles_cannot_change_ticket_priority(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(PermissionDenied):
        tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["l1"], priority="High", source="test")

    with pytest.raises(PermissionDenied):
        tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["responsible_a"], priority="High", source="test")


def test_change_ticket_priority_rejects_unknown_priority(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    with pytest.raises(ValidationError):
        tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["dm"], priority="Urgent", source="test")


def test_change_ticket_priority_upgrades_security_issue_normal_to_critical(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.change_ticket_type(db, ticket=ticket, actor=fixture_data["dm"], ticket_type="Security Issue", source="test")
    assert ticket.priority == "Critical"

    tickets.change_ticket_priority(db, ticket=ticket, actor=fixture_data["dm"], priority="Normal", source="test")
    assert ticket.priority == "Critical"


def test_priority_change_endpoint(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: fixture_data["dm"]
    try:
        response = TestClient(app).post(f"/api/tickets/{ticket.id}/priority", json={"priority": "High"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["priority"] == "High"


def test_in_progress_without_assignee_is_rejected(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    assert ticket.status == "Assigned"
    ticket.assignee_id = None
    db.flush()

    with pytest.raises(ValidationError, match="In progress status requires an assignee"):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")


def test_in_progress_with_assignee_is_allowed(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    assert ticket.status == "Assigned"

    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")

    assert ticket.status == "In progress"
    assert ticket.assignee_id == fixture_data["l1"].id


def test_l3_in_progress_requires_gitlab_issue(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L3", assignee_ref=fixture_data["l3"].email, source="test")
    link = db.scalar(select(GitLabLink).where(GitLabLink.ticket_id == ticket.id))
    if link:
        db.delete(link)
        db.flush()

    with pytest.raises(ConflictError):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l3"], new_status="In progress", source="test")


def test_only_admin_or_delivery_manager_can_close(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="In progress", source="test")
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Resolved", source="test")

    with pytest.raises(PermissionDenied):
        tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Closed", source="test")

    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["dm"], new_status="Closed", source="test")
    assert ticket.status == "Closed"


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
        team="L2",
        source="test",
    )

    assert ticket.owner_id == fixture_data["l2"].id
    assert tickets.can_view_ticket(db, fixture_data["l2"], ticket)
    assert ticket in tickets.list_visible_tickets(db, actor=fixture_data["l2"])


def test_resolver_roles_see_only_their_resolver_team(db, fixture_data):
    ticket = tickets.create_internal_ticket(
        db,
        actor=fixture_data["l2"],
        ticket_type="Operational Request",
        priority="Normal",
        title="Ticket owned by L2 but queued to L1",
        description="Resolver team visibility wins",
        team="L1",
        source="test",
    )

    assert ticket.owner_id == fixture_data["l2"].id
    assert not tickets.can_view_ticket(db, fixture_data["l2"], ticket)
    assert tickets.can_view_ticket(db, fixture_data["l1"], ticket)


def test_system_ticket_visibility_and_partner_comment_rules(db, fixture_data):
    ticket = tickets.create_system_ticket(
        db,
        partner_id=fixture_data["partner_a"].id,
        ticket_type="Operational Request",
        priority="Normal",
        title="System event",
        description="Created by integration",
        team="L1",
        source="test",
    )

    assert ticket.system is True
    assert ticket.partner_id == fixture_data["partner_a"].id
    assert ticket.client_id is None
    assert ticket.owner_id is None
    assert ticket.created_by_id is None
    assert tickets.can_view_ticket(db, fixture_data["responsible_a"], ticket)
    assert tickets.can_view_ticket(db, fixture_data["technical_a"], ticket)
    assert not tickets.can_view_ticket(db, fixture_data["responsible_b"], ticket)
    assert tickets.can_view_ticket(db, fixture_data["l1"], ticket)
    assert not tickets.can_view_ticket(db, fixture_data["l2"], ticket)

    comment = tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="Partner response", source="test")
    assert comment.body == "Partner response"
    with pytest.raises(PermissionDenied):
        tickets.add_comment(db, ticket=ticket, actor=fixture_data["technical_a"], body="Technical response", source="test")


def test_system_ticket_participants_are_managed_by_responsible_partner_user(db, fixture_data):
    ticket = tickets.create_system_ticket(
        db,
        partner_id=fixture_data["partner_a"].id,
        ticket_type="Operational Request",
        priority="Normal",
        title="System participant event",
        description="Created by integration",
        source="test",
    )

    tickets.add_participant(db, ticket=ticket, actor=fixture_data["responsible_a"], user_id=fixture_data["technical_a"].id, source="test")
    with pytest.raises(PermissionDenied):
        tickets.add_participant(db, ticket=ticket, actor=fixture_data["dm"], user_id=fixture_data["responsible_a"].id, source="test")
    with pytest.raises(ValidationError):
        tickets.transfer_owner(db, ticket=ticket, actor=fixture_data["dm"], new_owner_ref=fixture_data["responsible_a"].email, source="test")


def test_need_more_info_returns_after_public_comment(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    assert ticket.status == "Queued"
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["l1"], new_status="Need more info", source="test")

    tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="Here is the missing info", source="test")

    assert ticket.status == "Queued"


def test_need_more_info_without_resolver_team_returns_to_new(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.transition_ticket(db, ticket=ticket, actor=fixture_data["dm"], new_status="Need more info", source="test")

    tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="More details", source="test")

    assert ticket.status == "New"


def test_ticket_model_has_no_delete_flag(db, fixture_data):
    create_partner_ticket(db, fixture_data)
    assert db.scalar(select(Ticket)).status == "New"
    assert not hasattr(tickets, "delete_ticket")


def test_comment_edit_and_soft_delete_are_disabled(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    comment = tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="Original")

    with pytest.raises(PermissionDenied):
        tickets.edit_comment(db, comment=comment, actor=fixture_data["responsible_a"], body="Partner edit", source="test")

    with pytest.raises(PermissionDenied):
        tickets.edit_comment(db, comment=comment, actor=fixture_data["dm"], body="Edited", source="test")

    with pytest.raises(PermissionDenied):
        tickets.soft_delete_comment(db, comment=comment, actor=fixture_data["admin"], source="test")

    assert comment.body == "Original"
    assert comment.deleted_at is None


def test_client_update_keeps_responsible_assignments_intact(db, fixture_data):
    client = fixture_data["client_a"]

    admin.update_client(db, client_id=client.id, name="Renamed Client", actor=fixture_data["dm"], source="test")
    assert client.name == "Renamed Client"
    assert admin.list_client_assignments(db, client_id=client.id)


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


def test_delivery_manager_can_manage_non_admin_internal_users_and_admin_keeps_last_admin(db, fixture_data):
    admin.update_user(db, user_id=fixture_data["l1"].id, name="New L1", actor=fixture_data["dm"], source="test")
    assert fixture_data["l1"].name == "New L1"

    with pytest.raises(PermissionDenied):
        admin.update_user(db, user_id=fixture_data["admin"].id, name="New Admin", actor=fixture_data["dm"], source="test")

    with pytest.raises(PermissionDenied):
        admin.create_internal_user(db, email="admin-2@example.test", name="Admin 2", role="Admin", actor=fixture_data["dm"], source="test")

    with pytest.raises(ValidationError):
        admin.update_user(db, user_id=fixture_data["admin"].id, role="L1", actor=fixture_data["admin"], source="test")

    with pytest.raises(ValidationError):
        admin.deactivate_user_by_id(db, user_id=fixture_data["admin"].id, actor=fixture_data["admin"], source="test")


def test_partner_comment_notifications_follow_assignee_rule(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", source="test")
    tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="No assignee yet", source="test")
    assert db.scalar(select(Notification).where(Notification.event == "partner_comment", Notification.recipient_email == fixture_data["dm"].email))

    tickets.assign_ticket(db, ticket=ticket, actor=fixture_data["dm"], team="L1", assignee_ref=fixture_data["l1"].email, source="test")
    tickets.add_comment(db, ticket=ticket, actor=fixture_data["responsible_a"], body="Assignee should get this", source="test")
    assert db.scalar(select(Notification).where(Notification.event == "partner_comment", Notification.recipient_email == fixture_data["l1"].email))


def test_delivery_manager_can_create_partner_ticket_on_behalf(db, fixture_data):
    ticket = tickets.create_partner_ticket_on_behalf(
        db,
        actor=fixture_data["dm"],
        partner_id=fixture_data["partner_a"].id,
        owner_ref=fixture_data["responsible_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="Created by DM",
        description="Partner ticket created internally",
        client_id=fixture_data["client_a"].id,
        participant_ids=[fixture_data["technical_a"].id],
        source="test",
    )

    assert ticket.internal is False
    assert ticket.system is False
    assert ticket.partner_id == fixture_data["partner_a"].id
    assert ticket.owner_id == fixture_data["responsible_a"].id
    assert ticket.created_by_id == fixture_data["dm"].id
    assert tickets.can_view_ticket(db, fixture_data["responsible_a"], ticket)
    assert tickets.can_view_ticket(db, fixture_data["technical_a"], ticket)
    assert not tickets.can_view_ticket(db, fixture_data["responsible_b"], ticket)
    assert db.scalar(select(TicketParticipant).where(TicketParticipant.ticket_id == ticket.id, TicketParticipant.user_id == fixture_data["responsible_a"].id))
    assert db.scalar(select(TicketWatcher).where(TicketWatcher.ticket_id == ticket.id, TicketWatcher.user_id == fixture_data["responsible_a"].id))
    assert db.scalar(select(AuditLog).where(AuditLog.action == "ticket.create_partner_on_behalf", AuditLog.entity_id == ticket.id))
    assert db.scalar(select(Notification).where(Notification.event == "ticket_created_on_behalf", Notification.recipient_email == fixture_data["responsible_a"].email))


def test_l1_can_create_partner_ticket_on_behalf(db, fixture_data):
    ticket = tickets.create_partner_ticket_on_behalf(
        db,
        actor=fixture_data["l1"],
        partner_id=fixture_data["partner_a"].id,
        owner_ref=fixture_data["responsible_a"].id,
        ticket_type="Question",
        priority="Normal",
        title="Created by L1",
        description="Partner ticket from internal user",
        client_id=fixture_data["client_a"].id,
        source="test",
    )

    assert ticket.created_by_id == fixture_data["l1"].id
    assert tickets.can_view_ticket(db, fixture_data["l1"], ticket)
    assert ticket in tickets.list_visible_tickets(db, actor=fixture_data["l1"])
    assert tickets.can_view_ticket(db, fixture_data["responsible_a"], ticket)
    assert db.scalar(select(TicketWatcher).where(TicketWatcher.ticket_id == ticket.id, TicketWatcher.user_id == fixture_data["l1"].id))


def test_create_partner_ticket_on_behalf_rejects_invalid_roles_and_relationships(db, fixture_data):
    with pytest.raises(PermissionDenied):
        tickets.create_partner_ticket_on_behalf(
            db,
            actor=fixture_data["responsible_a"],
            partner_id=fixture_data["partner_a"].id,
            owner_ref=fixture_data["responsible_a"].id,
            ticket_type="Question",
            priority="Normal",
            title="Not allowed",
            description="Nope",
            source="test",
        )

    with pytest.raises(ValidationError):
        tickets.create_partner_ticket_on_behalf(
            db,
            actor=fixture_data["dm"],
            partner_id=fixture_data["partner_a"].id,
            owner_ref=fixture_data["technical_a"].id,
            ticket_type="Question",
            priority="Normal",
            title="Technical owner",
            description="Technical user cannot own the ticket",
            source="test",
        )

    client_b = admin.create_client(db, partner_key_or_id=fixture_data["partner_b"].id, name="Client B", source="test")
    with pytest.raises(ValidationError):
        tickets.create_partner_ticket_on_behalf(
            db,
            actor=fixture_data["dm"],
            partner_id=fixture_data["partner_a"].id,
            owner_ref=fixture_data["responsible_a"].id,
            ticket_type="Question",
            priority="Normal",
            title="Wrong client",
            description="Client belongs elsewhere",
            client_id=client_b.id,
            source="test",
        )


def _read_xlsx_sheet(content: bytes, sheet_index: int = 1) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return archive.read(f"xl/worksheets/sheet{sheet_index}.xml").decode("utf-8")


def _xlsx_sheet_names(content: bytes) -> list[str]:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
    return re.findall(r'<sheet name="([^"]+)"', workbook)


def _xlsx_column_widths(sheet_xml: str) -> list[float]:
    return [float(match.group(1)) for match in re.finditer(r'<col min="\d+" max="\d+" width="([\d.]+)"', sheet_xml)]


def test_ticket_export_hides_internal_data_from_partner_and_keeps_partner_isolation(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.add_internal_note(db, ticket=ticket, actor=fixture_data["dm"], body="Internal only", source="test")
    db.add(
        GitLabLink(
            id=new_id(),
            ticket_id=ticket.id,
            is_main=True,
            project_id="project",
            issue_iid="42",
            web_url="https://gitlab.example.test/issues/42",
            status="Open",
        )
    )
    tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_b"],
        ticket_type="Question",
        priority="Normal",
        title="Other partner",
        description="Must not leak",
        source="test",
    )
    db.commit()

    result = ticket_exports.build_ticket_export(db, actor=fixture_data["responsible_a"], export_format="xlsx", filters={})

    assert result.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    sheet_names = _xlsx_sheet_names(result.content)
    assert "Internal notes" not in sheet_names
    assert "Audit" not in sheet_names
    tickets_sheet = _read_xlsx_sheet(result.content)
    assert tickets_sheet.count("<row ") == 2
    assert "Internal only" not in tickets_sheet
    assert "web_url" not in tickets_sheet

    gitlab_sheet_index = _xlsx_sheet_names(result.content).index("GitLab") + 1
    gitlab_sheet = _read_xlsx_sheet(result.content, gitlab_sheet_index)
    assert "Open" in gitlab_sheet


def test_internal_ticket_export_formats_include_allowed_internal_data(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    tickets.add_internal_note(db, ticket=ticket, actor=fixture_data["dm"], body="Internal note", source="test")
    db.add(
        GitLabLink(
            id=new_id(),
            ticket_id=ticket.id,
            is_main=True,
            project_id="project",
            issue_iid="7",
            web_url="https://gitlab.example.test/issues/7",
            status="Open",
        )
    )
    db.commit()

    xlsx_result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={})
    sheet_names = _xlsx_sheet_names(xlsx_result.content)
    assert {"Tickets", "Internal notes", "Audit", "GitLab"}.issubset(set(sheet_names))

    tickets_sheet = _read_xlsx_sheet(xlsx_result.content)
    assert "HYPERLINK" in tickets_sheet
    assert f"/#/tickets/{ticket.id}" in tickets_sheet
    header = next(re.finditer(r"<row r=\"1\">(.*?)</row>", tickets_sheet, re.DOTALL)).group(1)
    for label in [label for _, label in ticket_exports.TICKET_EXPORT_COLUMNS]:
        assert label in header

    internal_notes_index = sheet_names.index("Internal notes") + 1
    internal_notes_sheet = _read_xlsx_sheet(xlsx_result.content, internal_notes_index)
    assert "Internal note" in internal_notes_sheet

    with zipfile.ZipFile(BytesIO(xlsx_result.content)) as archive:
        assert "xl/workbook.xml" in archive.namelist()
        assert "xl/worksheets/sheet1.xml" in archive.namelist()


def test_ticket_export_respects_filters_and_rejects_unknown_format(db, fixture_data):
    create_partner_ticket(db, fixture_data)
    tickets.create_partner_ticket(
        db,
        actor=fixture_data["responsible_a"],
        ticket_type="Question",
        priority="High",
        title="High priority",
        description="Filtered ticket",
        client_id=fixture_data["client_a"].id,
        source="test",
    )
    db.commit()

    result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={"priority": "High"})
    tickets_sheet = _read_xlsx_sheet(result.content)
    assert result.ticket_count == 1
    assert "High" in tickets_sheet

    for unsupported_format in ("json", "csv", "pdf"):
        with pytest.raises(ValidationError, match="Only Excel \\(xlsx\\) export is supported"):
            ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format=unsupported_format, filters={})


def test_format_ticket_export_datetime():
    value = datetime(2026, 6, 2, 11, 11, tzinfo=timezone.utc)
    assert ticket_exports.format_ticket_export_datetime(value) == "02.06.2026 13:11"


def test_ticket_export_formats_created_and_updated_as_czech_datetime(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    known = datetime(2026, 6, 2, 11, 11, tzinfo=timezone.utc)
    ticket.created_at = known
    ticket.updated_at = known
    db.commit()

    xlsx_result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={})
    tickets_sheet = _read_xlsx_sheet(xlsx_result.content)
    assert "02.06.2026 13:11" in tickets_sheet


def test_ticket_export_ticket_url_uses_app_base_url(db, fixture_data, monkeypatch):
    monkeypatch.setattr(
        ticket_exports,
        "settings",
        replace(ticket_exports.settings, base_url="https://tickets.example.test"),
    )
    ticket = create_partner_ticket(db, fixture_data)

    result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={})
    tickets_sheet = _read_xlsx_sheet(result.content)

    assert f"https://tickets.example.test/#/tickets/{ticket.id}" in tickets_sheet


def test_ticket_export_ticket_url_uses_production_base_url(db, fixture_data, monkeypatch):
    monkeypatch.setattr(
        ticket_exports,
        "settings",
        replace(ticket_exports.settings, base_url="https://ticketmaster.cermofi.cz"),
    )
    ticket = create_partner_ticket(db, fixture_data)

    result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={})
    tickets_sheet = _read_xlsx_sheet(result.content)

    assert f"https://ticketmaster.cermofi.cz/#/tickets/{ticket.id}" in tickets_sheet
    assert "localhost" not in tickets_sheet


def test_export_endpoint_audits_export_metadata(db, fixture_data):
    create_partner_ticket(db, fixture_data)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: fixture_data["dm"]
    try:
        response = TestClient(app).get("/api/tickets/export?format=xlsx")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    row = db.scalar(select(AuditLog).where(AuditLog.action == "tickets.export"))
    assert row
    assert row.new_value["format"] == "xlsx"
    assert row.new_value["ticket_count"] == 1


def test_export_endpoint_rejects_non_excel_formats(db, fixture_data):
    create_partner_ticket(db, fixture_data)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = lambda: fixture_data["dm"]
    try:
        for unsupported_format in ("json", "csv", "pdf"):
            response = TestClient(app).get(f"/api/tickets/export?format={unsupported_format}")
            assert response.status_code == 400
            assert response.json()["detail"] == "Only Excel (xlsx) export is supported"
    finally:
        app.dependency_overrides.clear()


def test_xlsx_column_widths_are_autosized(db, fixture_data):
    ticket = create_partner_ticket(db, fixture_data)
    ticket.title = "Short"
    db.commit()

    short_result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={})
    short_widths = _xlsx_column_widths(_read_xlsx_sheet(short_result.content))
    assert len(short_widths) == len(ticket_exports.TICKET_EXPORT_COLUMNS)
    assert all(ticket_exports.XLSX_MIN_COLUMN_WIDTH <= width <= ticket_exports.XLSX_MAX_COLUMN_WIDTH for width in short_widths)

    ticket.title = "x" * 200
    db.commit()
    long_result = ticket_exports.build_ticket_export(db, actor=fixture_data["admin"], export_format="xlsx", filters={})
    long_widths = _xlsx_column_widths(_read_xlsx_sheet(long_result.content))
    title_index = [label for _, label in ticket_exports.TICKET_EXPORT_COLUMNS].index("Topic")
    assert long_widths[title_index] == ticket_exports.XLSX_MAX_COLUMN_WIDTH
    assert long_widths[title_index] > short_widths[title_index]
