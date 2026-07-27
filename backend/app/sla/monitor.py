"""SLA breach/escalation monitor (Implementation Plan Phase 6; App Flow §16).

A background loop (started from the app lifespan, TRD §11) scans open tickets:
 - warning: resolution deadline within `sla_warning_minutes` → notify assignee
 - breach:  resolution deadline passed → escalate to the team lead + notify

Each fires once per ticket via the notifications trail, and each also fires
the matching automation trigger (`sla_warning` / `sla_breached`).
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.config import get_settings
from app.models import Ticket
from app.notifications import service as notifications
from app.webhooks import service as webhooks
from app.workflow import automation

logger = logging.getLogger("agentdesk")

# statuses whose resolution clock is live — on_hold is paused (§16), terminal are done
ACTIVE_STATUSES = ("new", "open", "in_progress", "reopened")


async def _candidates(session: AsyncSession, cutoff: datetime) -> list[Ticket]:
    result = await session.execute(
        sa.select(Ticket).where(
            Ticket.status.in_(ACTIVE_STATUSES),
            Ticket.merged_into_ticket_id.is_(None),
            Ticket.resolution_due_at.is_not(None),
            Ticket.resolution_due_at <= cutoff,
        )
    )
    return list(result.scalars())


async def scan_once(session: AsyncSession) -> int:
    """One pass; returns how many warning/breach events fired. Caller commits."""
    now = datetime.now(UTC)
    fired = 0
    for ticket in await _candidates(
        session, now + timedelta(minutes=get_settings().sla_warning_minutes)
    ):
        breached = ticket.resolution_due_at <= now
        trigger = "sla_breached" if breached else "sla_warning"
        # ponytail: one notification per (ticket, trigger) ever — a reopened
        # segment won't re-warn; track per-segment state if that starts to matter
        if await notifications.already_notified(session, ticket.id, trigger):
            continue
        ref = f"AGT-{ticket.display_id}"
        if breached:
            lead = await automation._find_team_lead(session, ticket)
            if lead is None:
                # no notification row written, so this retries next scan
                logger.warning("SLA breach on %s but no team lead to escalate to", ticket.id)
                continue
            before = {"assignee_id": str(ticket.assignee_id)}
            ticket.assignee_id = lead.id
            ticket.updated_at = now
            audit.log(
                session,
                "ticket",
                ticket.id,
                None,
                "sla_escalated",
                before=before,
                after={"assignee_id": str(lead.id)},
            )
            await notifications.notify(
                session,
                lead.id,
                ticket.id,
                trigger,
                f"[{ref}] SLA breached — escalated to you",
                f"Ticket {ref} passed its resolution deadline "
                f"({ticket.resolution_due_at:%Y-%m-%d %H:%M UTC}) and was escalated.",
            )
        else:
            if ticket.assignee_id is None:
                continue  # §16 warns the assigned agent; fires once assigned
            await notifications.notify(
                session,
                ticket.assignee_id,
                ticket.id,
                trigger,
                f"[{ref}] SLA warning",
                f"Ticket {ref} is due at {ticket.resolution_due_at:%Y-%m-%d %H:%M UTC}.",
            )
        await automation.dispatch(session, trigger, ticket)
        if breached:
            webhooks.dispatch(trigger, webhooks.ticket_payload(trigger, ticket))
        fired += 1
    return fired


async def run_forever(interval_seconds: int) -> None:
    from app.db import _session_factory

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            async with _session_factory() as session:
                fired = await scan_once(session)
                await session.commit()
                if fired:
                    logger.info("SLA monitor fired %d event(s)", fired)
        except Exception:
            logger.exception("SLA monitor scan failed")
