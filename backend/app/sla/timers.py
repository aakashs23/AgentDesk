"""SLA timer math (App Flow Doc 03 §16; policies from Document 05 `sla_policies`).

Phase 4 owns setting/moving the due-at columns; breach detection and
escalation jobs arrive in Phase 6.
"""

import uuid
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SlaPolicy, Ticket


async def policy_for(
    session: AsyncSession, category_id: uuid.UUID | None, priority_id: uuid.UUID | None
) -> SlaPolicy | None:
    """Most specific match wins: (category, priority) → (any category, priority)."""
    if priority_id is None:
        return None  # sla_policies always keys on priority (Doc 05) — nothing to match yet
    result = await session.execute(
        sa.select(SlaPolicy)
        .where(
            SlaPolicy.priority_id == priority_id,
            sa.or_(SlaPolicy.category_id == category_id, SlaPolicy.category_id.is_(None)),
        )
        .order_by(SlaPolicy.category_id.is_(None))  # exact category match sorts first
        .limit(1)
    )
    return result.scalar_one_or_none()


async def start_timers(session: AsyncSession, ticket: Ticket, start: datetime) -> None:
    """Set both due-at columns from the matching policy, anchored at `start`.

    Called on creation and again on first classification: an unclassified ticket has
    no priority, hence no matching policy — its timers still conceptually started at
    creation, so due dates are computed from created_at once a priority exists.
    """
    if ticket.response_due_at or ticket.resolution_due_at:
        return  # already running — never restart timers on later edits
    policy = await policy_for(session, ticket.category_id, ticket.priority_id)
    if policy:
        ticket.response_due_at = start + timedelta(minutes=policy.response_minutes)
        ticket.resolution_due_at = start + timedelta(minutes=policy.resolution_minutes)


async def fresh_resolution_segment(session: AsyncSession, ticket: Ticket, start: datetime) -> None:
    """Reopen: a brand-new resolution segment from `start` — never resumes the old clock."""
    policy = await policy_for(session, ticket.category_id, ticket.priority_id)
    if policy:
        ticket.resolution_due_at = start + timedelta(minutes=policy.resolution_minutes)


def resume_after_hold(ticket: Ticket, hold_started_at: datetime, now: datetime) -> None:
    """on_hold pauses the resolution timer: push the deadline out by the hold duration."""
    if ticket.resolution_due_at:
        ticket.resolution_due_at += now - hold_started_at
