from __future__ import annotations

import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ticketmaster.core.config import settings
from ticketmaster.models import Notification
from ticketmaster.models.entities import new_id


def queue_email(
    db: Session,
    *,
    event: str,
    recipient_email: str,
    subject: str,
    body: str,
    ticket_id: str | None,
) -> Notification:
    row = Notification(
        id=new_id(),
        ticket_id=ticket_id,
        event=event,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        status="pending",
    )
    db.add(row)
    return row


def send_notification(notification: Notification) -> None:
    if settings.mail_suppress_send:
        notification.status = "sent"
        notification.sent_at = datetime.now(timezone.utc)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = notification.recipient_email
    message["Subject"] = notification.subject
    message.set_content(notification.body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password or "")
        smtp.send_message(message)
    notification.status = "sent"
    notification.sent_at = datetime.now(timezone.utc)
    notification.last_error = None


def retry_failed(db: Session) -> int:
    db.flush()
    pending = db.scalars(select(Notification).where(Notification.status.in_(["pending", "failed"]))).all()
    sent = 0
    for notification in pending:
        try:
            notification.attempts += 1
            send_notification(notification)
            sent += 1
        except Exception as exc:  # pragma: no cover - depends on external SMTP
            notification.status = "failed"
            notification.last_error = str(exc)
    db.flush()
    return sent
