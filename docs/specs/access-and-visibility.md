# Access and visibility rules

Contract for ticket visibility and internal resolver access. Backend tests in
`backend/tests/test_business_rules.py` enforce these rules.

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
