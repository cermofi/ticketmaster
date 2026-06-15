from __future__ import annotations

from ticketmaster.models import User
from ticketmaster.models.constants import INTERNAL_ROLES, RESOLVER_TEAMS
from ticketmaster.services.errors import ValidationError

MAX_INTERNAL_ROLES = 3
ADMIN_DM_ROLES = frozenset({"Admin", "DeliveryManager"})


def get_internal_roles(user: User) -> list[str]:
    if user.kind != "internal":
        return []
    if user.internal_roles:
        return [role for role in user.internal_roles if isinstance(role, str) and role]
    if user.internal_role:
        return [user.internal_role]
    return []


def user_has_internal_role(user: User, role: str) -> bool:
    return role in get_internal_roles(user)


def user_has_any_internal_role(user: User, roles: set[str] | frozenset[str]) -> bool:
    return bool(set(get_internal_roles(user)) & set(roles))


def get_user_resolver_teams(user: User) -> set[str]:
    return set(get_internal_roles(user)) & RESOLVER_TEAMS


def normalize_internal_roles(roles: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for role in roles:
        item = role.strip()
        if not item or item in seen:
            continue
        if item not in INTERNAL_ROLES:
            raise ValidationError(f"Unsupported internal role: {item}")
        seen.add(item)
        cleaned.append(item)
    if not cleaned:
        raise ValidationError("At least one internal role is required")
    if len(cleaned) > MAX_INTERNAL_ROLES:
        raise ValidationError(f"Internal users can have at most {MAX_INTERNAL_ROLES} roles")
    return cleaned


def resolve_internal_role_input(*, role: str | None = None, roles: list[str] | None = None) -> list[str]:
    if roles is not None:
        return normalize_internal_roles(roles)
    if role is not None:
        return normalize_internal_roles([role])
    raise ValidationError("At least one internal role is required")


def set_internal_roles(user: User, roles: list[str]) -> None:
    normalized = normalize_internal_roles(roles)
    user.internal_roles = normalized
    user.internal_role = normalized[0]


def user_is_active_admin(user: User) -> bool:
    return user.kind == "internal" and user.active and user_has_internal_role(user, "Admin")


def assignee_has_resolver_team(user: User, team: str) -> bool:
    return user.kind == "internal" and user.active and user_has_internal_role(user, team)
