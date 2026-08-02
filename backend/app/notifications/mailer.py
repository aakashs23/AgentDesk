"""Minimal email delivery. Phase 7 builds the real Notification Service on top."""

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("agentdesk.mailer")


def send_email(to: str, subject: str, body: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        # Dev sandbox inbox: the email lands in the structured log instead of SMTP
        logger.info("email (smtp not configured) to=%s subject=%r body=%r", to, subject, body)
        return
    message = EmailMessage()
    message["From"] = settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)
    except OSError as exc:
        # ponytail: log and swallow. Callers (invite, reset, ack, notifications) have
        # already committed their row; a dead relay must not 500 the request or roll
        # that back. Add a retry queue when delivery has to be guaranteed.
        logger.error("email delivery failed to=%s subject=%r: %s", to, subject, exc)
