"""Minimal notification writes for Phase 6 triggers (SLA warning/escalation,
automation `notify` actions). Phase 7 builds the full template-driven
Notification Service on top; these rows already land in `notifications` so
in-app delivery history is correct from day one.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, User
from app.notifications import mailer


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    ticket_id: uuid.UUID | None,
    trigger_type: str,
    subject: str,
    message: str,
) -> None:
    """One in-app notifications row + best-effort email (logs when SMTP unset)."""
    session.add(
        Notification(
            user_id=user_id,
            ticket_id=ticket_id,
            trigger_type=trigger_type,
            channel="in_app",
            payload={"subject": subject, "message": message},
        )
    )
    user = await session.get(User, user_id)
    if user:
        mailer.send_email(user.email, subject, message)


async def already_notified(session: AsyncSession, ticket_id: uuid.UUID, trigger_type: str) -> bool:
    result = await session.execute(
        sa.select(Notification.id)
        .where(Notification.ticket_id == ticket_id, Notification.trigger_type == trigger_type)
        .limit(1)
    )
    return result.first() is not None
