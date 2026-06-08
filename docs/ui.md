# UI Guide

TicketMaster uses React, Reactstrap, Bootstrap 5, Bootstrap Icons, ASAB WebUI shell components and one shared SCSS stylesheet. Keep the product structure simple: tickets, admin, audit and settings are operational screens, not marketing pages.

## Design Tokens

Use the CSS variables in `frontend/src/styles.scss` before adding new colors or spacing:

- Spacing: `--tm-space-1` through `--tm-space-6`; common gaps are `--tm-space-2`, section gaps are `--tm-space-4`.
- Surfaces: `--tm-surface` for the app background, `--tm-panel` for panels and forms, `--tm-panel-soft` for subtle nested rows.
- Borders: `--tm-line` for standard borders, `--tm-line-strong` only for stronger separation.
- Radius: `--tm-radius` for panels/forms/modals, `--tm-radius-sm` for buttons and fields.
- Status colors: use `StatusPill` instead of custom badge colors when representing workflow or priority state.

## Typography

- Page titles use `PageHeader`; avoid ad hoc `h1.h4` combinations.
- Panel headings are `h2`/`h3` inside `.tm-panel` and should stay compact.
- Labels should use Reactstrap `Label`; avoid placeholder-only inputs.
- Body text should stay sentence case. Table headers may be uppercase through CSS only.

## Layout

- Every screen starts with `.tm-screen` and a `PageHeader`.
- Use `.tm-panel` for grouped content and `.tm-form-page` for a single focused form.
- Use grid helpers already defined for major layouts: `.tm-ticket-layout`, `.tm-admin-layout`, `.tm-toolbar`, `.tm-admin-filters`.
- Do not put panels inside panels. Use rows such as `.tm-responsible-row` for nested repeated content.
- Avoid inline styles. Add a named CSS class when a style repeats or expresses layout.

## Buttons

- Primary actions use `color="primary"`.
- Secondary actions use `outline color="secondary"`.
- Destructive actions use `outline color="danger"` and must be disabled when unavailable.
- Icon-only buttons must have a `title` or accessible label.
- Button text should describe the command; icons are supporting cues.

## Forms

- Each input must have a visible label.
- Keep related controls in `FormGroup`.
- Disable submit buttons until required fields are present.
- Use full-width submit buttons in narrow side panels and focused form pages.
- Use switches for binary settings where the value is a state, not a one-off acknowledgement.

## Tables And Lists

- Wrap tables in `.tm-table-wrap` and use `.tm-table`.
- Use `EmptyRow` for empty table states and `EmptyState` for non-table empty sections.
- Keep row actions right-aligned and icon buttons grouped.
- Long identifiers can be shortened in display, but links must still point to the full route/entity.

## Alerts, Loading And Empty States

- Use `ErrorBanner` for API errors.
- Use `Loading` for initial page loads.
- Empty states should explain the state briefly and avoid blaming the user.
- Avoid raw JSON dumps unless the screen is explicitly technical, such as Audit.

## Responsive Behavior

- Main grids collapse to one column below 960px.
- Page headers stack below 640px and actions become full-width.
- Table overflow is horizontal inside `.tm-table-wrap`.
- Keep fixed side panels sticky only on desktop.

## Accessibility

- Preserve semantic headings and form labels.
- Use visible focus states from shared CSS.
- Prefer real buttons for actions and links for navigation.
- Use `aria-live` only for loading or async status messages that need announcement.
- Keep color contrast readable in both default and high contrast settings.

## Existing Product Rules

- Navigation contains Tickets, Vytvořit ticket, Admin, Audit and Nastavení.
- Partner users do not see internal-only administration and audit links.
- Ticket detail keeps description and communication in the main area; metadata and actions stay in the right panel.
- Partner users see only the current ticket status; internal users see only valid status transitions.
- Responsible people are managed from the client edit dialog in Admin.
- Partner roles are displayed as `Odpovědná osoba` and `Technická osoba`.
