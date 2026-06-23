# Access and visibility rules

Contract for ticket visibility and internal resolver access. The authoritative
machine-readable matrix lives in
`backend/ticketmaster/policy/access_matrix.json`. Backend contract tests in
`backend/tests/test_policy_contract.py` iterate matrix scenarios.

## Roles

| Actor | Scope |
| --- | --- |
| Admin, Delivery Manager | All tickets |
| L1 / L2 / L3 (resolver roles) | Tickets whose `resolver_team` matches one of the user's resolver roles |
| Internal without resolver role | Tickets they created (`created_by_id`) |
| Partner user | Non-internal tickets for their partner |

## Resolver team visibility (contentious rule)

When an internal user holds one or more resolver roles (L1, L2, L3):

### Internal tickets (`internal=true`)

Visibility is determined **only by `resolver_team`**, not by ownership or creation.

Examples:

1. L2 creates an internal ticket assigned to resolver team **L1**. L2 is recorded
   as owner/creator but **cannot view** the ticket. L1 users **can view** it.
2. L2 creates an internal ticket assigned to resolver team **L2**. L2 **can view**
   it because `resolver_team` matches their role.

### Partner and system tickets (`internal=false`)

Resolver users see tickets when **any** of these hold:

- `resolver_team` matches one of their resolver roles
- they are the current `assignee_id`
- they are the `created_by_id` (e.g. on-behalf creation)

Rationale: internal queue routing is strict; partner-facing work still grants access
to the assignee and creating internal user.

## Internal → partner on-behalf creation (intentional)

When an internal user creates a partner ticket on behalf (`create_partner_on_behalf`):

- **Status** is set to `Assigned` (not `New`).
- **Assignee** is the creating internal user (`assignee_id = actor.id`).

This is deliberate product intent so the creator owns follow-up. Documented in
`access_matrix.json` under `action_rules.create_partner_on_behalf.intent` and
covered by contract tests.

## Partner and system tickets

- Partner users never see `internal=true` tickets.
- System tickets follow partner visibility; resolver teams see them when
  `resolver_team` matches (same rule as above for internal resolvers).

## Audit suppression

- All HTTP API traffic is audited.
- Audit suppression is allowed **only** inside trusted internal code paths via
  the `suppress_audit()` context manager (CLI smoke cleanup, internal scripts).
- HTTP headers must **not** suppress audit on public requests.

## Session impersonation

- `sign-in-as-partner` returns a one-time `return_token` stored client-side.
- `back-to-admin` requires the partner JWT plus matching `return_token`.
- Return token is single-use and invalidated after successful return.

## Frontend session/query invalidation

Central store: `frontend/src/api/queryStore.js`.

| Transition | Invalidated domains |
| --- | --- |
| login | session, meta, tickets, ticketDetail, audit, admin, account, partners, clients, users, partnerOverview |
| logout | all domains |
| impersonationStart | same as login |
| impersonationEnd | same as login |
| sessionRefresh | session, account |

Screens register domain refetch handlers via `useSessionDomainRefresh`. Hard reload
is fallback only when soft session finalization cannot proceed.
