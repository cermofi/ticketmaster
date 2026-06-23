from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from ticketmaster.models import Ticket, User
from ticketmaster.services.internal_roles import ADMIN_DM_ROLES, get_internal_roles, get_user_resolver_teams

MATRIX_PATH = Path(__file__).with_name("access_matrix.json")


@lru_cache(maxsize=1)
def load_access_matrix() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def get_action_rule(action: str) -> dict[str, Any] | None:
    for row in load_access_matrix().get("action_rules", []):
        if row.get("action") == action:
            return row
    return None


def evaluate_visibility(user: User, ticket: Ticket) -> bool:
    """Authoritative visibility check aligned with access_matrix.json."""
    if user.kind == "internal":
        if set(get_internal_roles(user)) & ADMIN_DM_ROLES:
            return True
        resolver_teams = get_user_resolver_teams(user)
        if resolver_teams:
            if ticket.internal:
                return ticket.resolver_team in resolver_teams
            return (
                ticket.resolver_team in resolver_teams
                or ticket.assignee_id == user.id
                or ticket.created_by_id == user.id
            )
        if ticket.created_by_id == user.id:
            return True
        return False
    if ticket.internal:
        return False
    return ticket.partner_id == user.partner_id
