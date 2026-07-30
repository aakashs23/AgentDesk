"""Notification Service (Phase 7; App Flow §17).

`notify(...)` is the single fan-out point every trigger calls. For a firing
event it resolves the recipient's per-trigger channel preferences, and for each
enabled channel looks up the active `notification_templates` row for
`(trigger, channel)`, interpolates the ticket/user variables, writes a
`notifications` row (with `template_id` when a template rendered it), and
dispatches via the matching channel adapter. When no active template exists it
falls back to the system-default `subject`/`message` the caller passes
(Doc 05 note on `is_active`).
"""

import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationTemplate, Ticket, User
from app.notifications import mailer, templates

CHANNELS = templates.CHANNELS


def channels_for(user: User, trigger_type: str) -> list[str]:
    """Enabled channels for this recipient+trigger. Absent pref = channel on.

    Preference shape (`users.notification_preferences`):
    `{"sla_warning": {"email": false, "in_app": true}, ...}`.
    """
    prefs = user.notification_preferences or {}
    per_trigger = prefs.get(trigger_type, {})
    return [c for c in CHANNELS if per_trigger.get(c, True)]


async def _active_template(
    session: AsyncSession, trigger_type: str, channel: str
) -> NotificationTemplate | None:
    result = await session.execute(
        sa.select(NotificationTemplate)
        .where(
            NotificationTemplate.trigger_type == trigger_type,
            NotificationTemplate.channel == channel,
            NotificationTemplate.is_active.is_(True),
        )
        .order_by(NotificationTemplate.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def notify(
    session: AsyncSession,
    user_id: uuid.UUID,
    ticket_id: uuid.UUID | None,
    trigger_type: str,
    subject: str,
    message: str,
    override_template: bool = False,
) -> None:
    """Fan out one event to every channel the recipient has enabled for it.

    `subject`/`message` are a fallback the active template wins over — except
    with `override_template`, for copy a human wrote for this one event (an
    automation rule's message) which a generic template would otherwise discard.
    """
    user = await session.get(User, user_id)
    if user is None:
        return
    ticket = await session.get(Ticket, ticket_id) if ticket_id else None
    for channel in channels_for(user, trigger_type):
        template = await _active_template(session, trigger_type, channel)
        if template and not override_template:
            rendered_subject = (
                templates.render(template.subject_template, ticket, user)
                if template.subject_template
                else subject
            )
            rendered_body = templates.render(template.body_template, ticket, user)
            template_id = template.id
        else:
            rendered_subject, rendered_body, template_id = subject, message, None
        session.add(
            Notification(
                user_id=user_id,
                ticket_id=ticket_id,
                template_id=template_id,
                trigger_type=trigger_type,
                channel=channel,
                payload={"subject": rendered_subject, "message": rendered_body},
            )
        )
        if channel == "email":
            mailer.send_email(user.email, rendered_subject, rendered_body)
        # in_app: the notifications row itself is the delivery


async def already_notified(session: AsyncSession, ticket_id: uuid.UUID, trigger_type: str) -> bool:
    result = await session.execute(
        sa.select(Notification.id)
        .where(Notification.ticket_id == ticket_id, Notification.trigger_type == trigger_type)
        .limit(1)
    )
    return result.first() is not None
