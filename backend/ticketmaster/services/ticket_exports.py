from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import (
    Attachment,
    AuditLog,
    Client,
    Comment,
    GitLabLink,
    Partner,
    Ticket,
    TicketParticipant,
    TicketWatcher,
    User,
)
from ticketmaster.services import tickets
from ticketmaster.services.errors import ValidationError
from ticketmaster.services.internal_roles import get_internal_roles, user_has_any_internal_role


@dataclass(frozen=True)
class ExportResult:
    content: bytes
    media_type: str
    filename: str
    ticket_count: int
    filters: dict[str, Any]


@dataclass
class Sheet:
    name: str
    key: str
    filename: str
    columns: list[str]
    rows: list[dict[str, Any]]


TICKET_EXPORT_DATETIME_FORMAT = "%d.%m.%Y %H:%M"
TICKET_EXPORT_DATETIME_TZ = ZoneInfo("Europe/Prague")
XLSX_MIN_COLUMN_WIDTH = 8.0
XLSX_MAX_COLUMN_WIDTH = 60.0
XLSX_COLUMN_WIDTH_PADDING = 2.0
SUPPORTED_EXPORT_FORMAT = "xlsx"

TICKET_EXPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("created_at", "Vytvořeno"),
    ("updated_at", "Aktualizováno"),
    ("partner_name", "Partner"),
    ("client_name", "Klient"),
    ("type", "Typ požadavku"),
    ("priority", "Priorita"),
    ("status", "Status"),
    ("resolver_team", "Resolver team"),
    ("assignee_name", "Asignee"),
    ("title", "Topic"),
    ("url", "URL"),
)

DELIVERY_TRACKING_EXPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("last_gitlab_update", "last update"),
    ("ticket_id", "ID"),
    ("delivery_issue", "delivery issue"),
    ("current_state", "Current state"),
    ("target_issue_url", "team id"),
    ("assignee", "Asignee"),
    ("labels", "Labels"),
    ("delivery_url", "delivery url"),
    ("target_issue_full_url", "target issue url"),
    ("target_team", "target team"),
    ("target_project", "target project"),
    ("sync_status", "sync status"),
    ("resolution_source", "resolution source"),
    ("last_synced_at", "last synced at"),
    ("sync_error", "sync error"),
)


def format_ticket_export_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(TICKET_EXPORT_DATETIME_TZ).strftime(TICKET_EXPORT_DATETIME_FORMAT)


def _ticket_detail_url(ticket_id: str) -> str:
    return f"{settings.base_url.rstrip('/')}/#/tickets/{ticket_id}"


def build_ticket_export(db: Session, *, actor: User, export_format: str, filters: dict[str, Any]) -> ExportResult:
    normalized_format = export_format.lower().strip() or SUPPORTED_EXPORT_FORMAT
    if normalized_format != SUPPORTED_EXPORT_FORMAT:
        raise ValidationError("Only Excel (xlsx) export is supported")

    clean_filters = {key: value for key, value in filters.items() if value not in (None, "")}
    rows = tickets.list_visible_tickets(
        db,
        actor=actor,
        search=clean_filters.get("search"),
        status=clean_filters.get("status"),
        priority=clean_filters.get("priority"),
        ticket_type=clean_filters.get("type"),
        resolver_team=clean_filters.get("resolver_team"),
        partner_id=clean_filters.get("partner_id"),
        internal=clean_filters.get("internal"),
    )
    if len(rows) > settings.export_ticket_max_count:
        raise ValidationError(f"Export contains too many tickets. Limit is {settings.export_ticket_max_count}.")

    sheets = _build_sheets(db, actor=actor, ticket_rows=rows)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    content = _xlsx_bytes(sheets)
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = f"ticketmaster_export_{timestamp}.xlsx"
    return ExportResult(content=content, media_type=media_type, filename=filename, ticket_count=len(rows), filters=clean_filters)


def build_delivery_tracking_export(
    db: Session,
    *,
    actor: User,
    export_format: str,
    filters: dict[str, Any],
    sort_by: str | None = None,
    sort_direction: str | None = None,
) -> ExportResult:
    normalized_format = export_format.lower().strip() or SUPPORTED_EXPORT_FORMAT
    if normalized_format != SUPPORTED_EXPORT_FORMAT:
        raise ValidationError("Only Excel (xlsx) export is supported")
    if actor.kind != "internal":
        raise ValidationError("Delivery tracking export is internal only")

    from ticketmaster.services import gitlab_delivery_tracking

    clean_filters = {key: value for key, value in filters.items() if value not in (None, "")}
    normalized_sort_by, normalized_sort_direction = gitlab_delivery_tracking.normalize_sort(sort_by, sort_direction)
    updated_since = gitlab_delivery_tracking.parse_updated_since(clean_filters.get("updated_since"))
    rows_payload = gitlab_delivery_tracking.list_tracked_issues(
        db,
        search=clean_filters.get("search"),
        target_team=clean_filters.get("target_team"),
        state=clean_filters.get("state"),
        missing_mapping=clean_filters.get("missing_mapping"),
        assignee=clean_filters.get("assignee"),
        label=clean_filters.get("label"),
        updated_since=updated_since,
        sort_by=normalized_sort_by,
        sort_direction=normalized_sort_direction,
        limit=settings.export_ticket_max_count + 1,
        offset=0,
    )
    rows = rows_payload["items"]
    if len(rows) > settings.export_ticket_max_count:
        raise ValidationError(f"Export contains too many tracked issues. Limit is {settings.export_ticket_max_count}.")

    sheet_rows: list[dict[str, Any]] = []
    for row in rows:
        delivery_issue = row.get("delivery_title") or ""
        ticket_id = row.get("delivery_issue_iid") or ""
        labels_source = row.get("target_labels") or row.get("delivery_labels") or []
        labels = ", ".join(labels_source)
        assignee = _delivery_tracking_assignee_text(row.get("target_assignees"))
        last_gitlab_update = row.get("target_updated_at") or row.get("delivery_updated_at")
        last_synced_at = row.get("last_synced_at")
        current_state = row.get("target_state") or row.get("delivery_state") or ""
        in_delivery = row.get("sync_status") == "in_delivery"
        target_team = row.get("target_team_name") or ("Delivery" if in_delivery else "")
        target_project = row.get("target_project_name") or ""
        sync_status = _delivery_sync_status_label(row.get("sync_status"))
        if isinstance(last_gitlab_update, datetime):
            last_gitlab_update = format_ticket_export_datetime(last_gitlab_update)
        if isinstance(last_synced_at, datetime):
            last_synced_at = format_ticket_export_datetime(last_synced_at)
        sheet_rows.append(
            {
                "last update": last_gitlab_update or "",
                "ID": ticket_id,
                "delivery issue": delivery_issue,
                "Current state": current_state,
                "team id": row.get("target_issue_iid") or "",
                "Asignee": assignee,
                "Labels": labels,
                "delivery url": row.get("delivery_url") or "",
                "target issue url": row.get("target_url") or "",
                "target team": target_team,
                "target project": target_project,
                "sync status": sync_status,
                "resolution source": row.get("resolution_source") or "",
                "last synced at": last_synced_at or "",
                "sync error": row.get("sync_error") or "",
            }
        )

    columns = [label for _, label in DELIVERY_TRACKING_EXPORT_COLUMNS]
    sheet = Sheet(
        name="Delivery tracking",
        key="delivery_tracking",
        filename="delivery_tracking.csv",
        columns=columns,
        rows=sheet_rows,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M")
    content = _xlsx_bytes([sheet])
    media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    filename = f"delivery_tracking_{timestamp}.xlsx"
    return ExportResult(
        content=content,
        media_type=media_type,
        filename=filename,
        ticket_count=len(rows),
        filters={**clean_filters, "sort_by": normalized_sort_by, "sort_direction": normalized_sort_direction},
    )


def _build_sheets(db: Session, *, actor: User, ticket_rows: list[Ticket]) -> list[Sheet]:
    ticket_ids = [ticket.id for ticket in ticket_rows]
    internal_viewer = actor.kind == "internal"
    audit_viewer = internal_viewer and user_has_any_internal_role(actor, {"Admin", "DeliveryManager"})

    user_ids = {ticket.assignee_id for ticket in ticket_rows if ticket.assignee_id}
    users = _users_by_id(db, user_ids)
    partners = _partners_by_id(db, {ticket.partner_id for ticket in ticket_rows if ticket.partner_id})
    clients = _clients_by_id(db, {ticket.client_id for ticket in ticket_rows if ticket.client_id})
    gitlab_links = _gitlab_by_ticket_id(db, ticket_ids)

    ticket_columns = [label for _, label in TICKET_EXPORT_COLUMNS]

    ticket_data = []
    for ticket in ticket_rows:
        assignee = users.get(ticket.assignee_id)
        values = {
            "created_at": format_ticket_export_datetime(ticket.created_at) if ticket.created_at else None,
            "updated_at": format_ticket_export_datetime(ticket.updated_at) if ticket.updated_at else None,
            "partner_name": partners.get(ticket.partner_id).name if ticket.partner_id in partners else None,
            "client_name": clients.get(ticket.client_id).name if ticket.client_id in clients else None,
            "type": ticket.type,
            "priority": ticket.priority,
            "status": ticket.status,
            "resolver_team": ticket.resolver_team,
            "assignee_name": assignee.name if assignee else None,
            "title": ticket.title,
            "url": _ticket_detail_url(ticket.id),
        }
        ticket_data.append({label: values[key] for key, label in TICKET_EXPORT_COLUMNS})

    comment_columns = ["id", "ticket_id", "author_id", "author_name", "author_kind", "visibility", "body", "created_at"]
    comment_data: list[dict[str, Any]] = []
    internal_note_data: list[dict[str, Any]] = []
    if ticket_ids:
        comment_stmt = select(Comment).where(Comment.ticket_id.in_(ticket_ids), Comment.deleted_at.is_(None)).order_by(Comment.created_at.asc())
        if not internal_viewer:
            comment_stmt = comment_stmt.where(Comment.visibility == "comment")
        comments = list(db.scalars(comment_stmt).all())
        comment_users = _users_by_id(db, {comment.author_id for comment in comments if comment.author_id})
        for comment in comments:
            author = comment_users.get(comment.author_id)
            row = {
                "id": comment.id,
                "ticket_id": comment.ticket_id,
                "author_id": comment.author_id,
                "author_name": author.name if author else None,
                "author_kind": author.kind if author else None,
                "visibility": comment.visibility,
                "body": comment.body,
                "created_at": comment.created_at,
            }
            if comment.visibility == "internal_note":
                internal_note_data.append(row)
            else:
                comment_data.append(row)

    people_columns = ["ticket_id", "user_id", "name", "email", "kind", "role", "created_at"]
    participant_data = _ticket_people_rows(db, TicketParticipant, ticket_ids, internal_viewer=internal_viewer)
    watcher_data = _ticket_people_rows(db, TicketWatcher, ticket_ids, internal_viewer=internal_viewer)

    attachment_columns = [
        "id",
        "ticket_id",
        "comment_id",
        "filename",
        "content_type",
        "size_bytes",
        "uploaded_by_id",
        "uploaded_by_name",
        "created_at",
        "download_url",
    ]
    attachment_data: list[dict[str, Any]] = []
    if ticket_ids:
        attachments = list(db.scalars(select(Attachment).where(Attachment.ticket_id.in_(ticket_ids)).order_by(Attachment.created_at.asc())).all())
        uploaders = _users_by_id(db, {attachment.uploaded_by_id for attachment in attachments if attachment.uploaded_by_id})
        for attachment in attachments:
            uploader = uploaders.get(attachment.uploaded_by_id)
            attachment_data.append(
                {
                    "id": attachment.id,
                    "ticket_id": attachment.ticket_id,
                    "comment_id": attachment.comment_id,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "size_bytes": attachment.size_bytes,
                    "uploaded_by_id": attachment.uploaded_by_id,
                    "uploaded_by_name": uploader.name if uploader else None,
                    "created_at": attachment.created_at,
                    "download_url": f"/api/attachments/{attachment.id}/download",
                }
            )

    audit_columns = ["id", "entity_type", "entity_id", "action", "old_value", "new_value", "changed_by_user_id", "source", "changed_at"]
    audit_data: list[dict[str, Any]] = []
    if audit_viewer and ticket_ids:
        audit_rows = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.entity_type == "Ticket", AuditLog.entity_id.in_(ticket_ids))
                .order_by(AuditLog.changed_at.asc())
            ).all()
        )
        audit_data = [
            {
                "id": row.id,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "action": row.action,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "changed_by_user_id": row.changed_by_user_id,
                "source": row.source,
                "changed_at": row.changed_at,
            }
            for row in audit_rows
        ]

    gitlab_columns = ["ticket_id", "gitlab_status", "gitlab_issue_exists"]
    if internal_viewer:
        gitlab_columns.extend(["project_id", "issue_iid", "issue_id", "issue_state", "board_list", "web_url", "last_synced_at"])
    gitlab_data = []
    for ticket in ticket_rows:
        link = gitlab_links.get(ticket.id)
        row = {
            "ticket_id": ticket.id,
            "gitlab_status": link.status if link else None,
            "gitlab_issue_exists": link is not None,
        }
        if internal_viewer:
            row.update(
                {
                    "project_id": link.project_id if link else None,
                    "issue_iid": link.issue_iid if link else None,
                    "issue_id": link.issue_id if link else None,
                    "issue_state": link.issue_state if link else None,
                    "board_list": link.board_list if link else None,
                    "web_url": link.web_url if link else None,
                    "last_synced_at": link.last_synced_at if link else None,
                }
            )
        gitlab_data.append(row)

    sheets = [
        Sheet("Tickets", "tickets", "tickets.csv", ticket_columns, ticket_data),
        Sheet("Comments", "comments", "comments.csv", comment_columns, comment_data),
        Sheet("Participants", "participants", "participants.csv", people_columns, participant_data),
        Sheet("Watchers", "watchers", "watchers.csv", people_columns, watcher_data),
        Sheet("Attachments", "attachments", "attachments.csv", attachment_columns, attachment_data),
        Sheet("GitLab", "gitlab", "gitlab.csv", gitlab_columns, gitlab_data),
    ]
    if internal_viewer:
        sheets.insert(2, Sheet("Internal notes", "internal_notes", "internal_notes.csv", comment_columns, internal_note_data))
    if audit_viewer:
        sheets.insert(-1, Sheet("Audit", "audit", "audit.csv", audit_columns, audit_data))
    return sheets


def _ticket_people_rows(db: Session, model: type[TicketParticipant] | type[TicketWatcher], ticket_ids: list[str], *, internal_viewer: bool) -> list[dict[str, Any]]:
    if not ticket_ids:
        return []
    stmt = select(model, User).join(User, model.user_id == User.id).where(model.ticket_id.in_(ticket_ids)).order_by(model.created_at.asc())
    if not internal_viewer:
        stmt = stmt.where(User.kind == "partner")
    rows = []
    for relation, user in db.execute(stmt).all():
        rows.append(
            {
                "ticket_id": relation.ticket_id,
                "user_id": user.id,
                "name": user.name,
                "email": user.email,
                "kind": user.kind,
                "role": ", ".join(get_internal_roles(user)) if user.kind == "internal" else user.partner_role,
                "created_at": relation.created_at,
            }
        )
    return rows


def _users_by_id(db: Session, ids: set[str | None]) -> dict[str, User]:
    clean_ids = {row_id for row_id in ids if row_id}
    if not clean_ids:
        return {}
    return {user.id: user for user in db.scalars(select(User).where(User.id.in_(clean_ids))).all()}


def _partners_by_id(db: Session, ids: set[str | None]) -> dict[str, Partner]:
    clean_ids = {row_id for row_id in ids if row_id}
    if not clean_ids:
        return {}
    return {partner.id: partner for partner in db.scalars(select(Partner).where(Partner.id.in_(clean_ids))).all()}


def _clients_by_id(db: Session, ids: set[str | None]) -> dict[str, Client]:
    clean_ids = {row_id for row_id in ids if row_id}
    if not clean_ids:
        return {}
    return {client.id: client for client in db.scalars(select(Client).where(Client.id.in_(clean_ids))).all()}


def _gitlab_by_ticket_id(db: Session, ticket_ids: list[str]) -> dict[str, GitLabLink]:
    if not ticket_ids:
        return {}
    return {
        link.ticket_id: link
        for link in db.scalars(
            select(GitLabLink).where(GitLabLink.ticket_id.in_(ticket_ids), GitLabLink.is_main.is_(True))
        ).all()
    }


def _xlsx_bytes(sheets: list[Sheet]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(sheets)))
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheets))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml(len(sheets)))
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(sheet))
    return output.getvalue()


def _content_types_xml(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    overrides.extend(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'{"".join(overrides)}'
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheets: list[Sheet]) -> str:
    sheet_xml = "".join(
        f'<sheet name="{escape(sheet.name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, sheet in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_xml}</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml(sheet_count: int) -> str:
    rels = [
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(rels)}'
        "</Relationships>"
    )


def _styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        "</styleSheet>"
    )


def _column_widths(sheet: Sheet) -> list[float]:
    widths: list[float] = []
    for column in sheet.columns:
        max_length = len(column)
        for row in sheet.rows:
            max_length = max(max_length, len(_scalar_text(row.get(column))))
        width = max_length + XLSX_COLUMN_WIDTH_PADDING
        width = max(XLSX_MIN_COLUMN_WIDTH, min(XLSX_MAX_COLUMN_WIDTH, width))
        widths.append(width)
    return widths


def _cols_xml(widths: list[float]) -> str:
    columns = [
        f'<col min="{index}" max="{index}" width="{width:.2f}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    ]
    return f"<cols>{''.join(columns)}</cols>"


def _worksheet_xml(sheet: Sheet) -> str:
    hyperlink_indices = {
        index for index, column in enumerate(sheet.columns)
        if column.upper().endswith("URL")
    }
    rows = [_xlsx_row(1, sheet.columns)]
    for index, row in enumerate(sheet.rows, start=2):
        rows.append(_xlsx_row(index, [row.get(column) for column in sheet.columns], hyperlink_indices=hyperlink_indices))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{_cols_xml(_column_widths(sheet))}"
        f"<sheetData>{''.join(rows)}</sheetData>"
        "</worksheet>"
    )


def _xlsx_row(row_index: int, values: list[Any], *, hyperlink_indices: set[int] | None = None) -> str:
    hyperlink_indices = hyperlink_indices or set()
    cells = []
    for column_index, value in enumerate(values, start=1):
        cell_ref = f"{_excel_column(column_index)}{row_index}"
        if (column_index - 1) in hyperlink_indices and value:
            url = _xml_safe(_scalar_text(value)).replace('"', '""')
            cells.append(f'<c r="{cell_ref}"><f>HYPERLINK("{escape(url)}","{escape(url)}")</f></c>')
            continue
        text = escape(_xml_safe(_scalar_text(value)))
        cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>')
    return f'<row r="{row_index}">{"".join(cells)}</row>'


def _excel_column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True)
    return str(value)


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def _xml_safe(value: str) -> str:
    return "".join(char for char in value if char in "\n\r\t" or ord(char) >= 32)


def _delivery_tracking_assignee_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("username") or "").strip()
        if name:
            names.append(name)
    return ", ".join(names)


def _delivery_sync_status_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "ok":
        return "Synced"
    if text == "in_delivery":
        return "In delivery"
    if text == "target_missing":
        return "Target missing"
    if text == "error":
        return "Sync error"
    return str(value or "")


