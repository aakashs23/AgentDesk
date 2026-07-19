"""Ticket lifecycle state machine — the transition table from App Flow Doc 03 §10.

Every status change in the system goes through `transition()` (or `record()` for
the documented merge variant), which is the single place that writes BOTH
`ticket_status_history` and `audit_logs` and applies SLA timer effects.
Anything not in the table is rejected here, not at the router.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.models import Ticket, TicketStatusHistory
from app.sla import timers

STATUSES = {"new", "open", "in_progress", "on_hold", "resolved", "closed", "reopened"}

# (from, to) → roles that may perform it manually; system (role=None) may perform any.
# Mirrors the "Who Can Perform It" column of App Flow Doc 03 §10 exactly.
_STAFF = {"agent", "team_lead", "admin"}
TRANSITIONS: dict[tuple[str, str], set[str]] = {
    ("new", "open"): _STAFF,
    ("open", "in_progress"): _STAFF,
    ("in_progress", "on_hold"): _STAFF,
    ("on_hold", "in_progress"): _STAFF,
    ("in_progress", "resolved"): _STAFF,
    ("resolved", "closed"): _STAFF,
    ("closed", "reopened"): {"requester"} | _STAFF,  # requester = own ticket, checked upstream
    ("reopened", "in_progress"): set(),  # automatic re-entry only
}


def _now() -> datetime:
    return datetime.now(UTC)


def _record(
    session: AsyncSession,
    ticket: Ticket,
    old: str | None,
    new: str,
    actor_id: uuid.UUID | None,
    action: str = "status_changed",
) -> None:
    """The invariant: one status change = one row in each of the two tables."""
    session.add(
        TicketStatusHistory(
            ticket_id=ticket.id, old_status=old, new_status=new, changed_by=actor_id
        )
    )
    audit.log(
        session,
        "ticket",
        ticket.id,
        actor_id,
        action,
        before={"status": old},
        after={"status": new},
    )


def record_created(session: AsyncSession, ticket: Ticket, actor_id: uuid.UUID | None) -> None:
    """Initial — → new row (old_status null per Document 05)."""
    _record(session, ticket, None, "new", actor_id, action="created")


async def _hold_started_at(session: AsyncSession, ticket_id: uuid.UUID) -> datetime | None:
    result = await session.execute(
        sa.select(TicketStatusHistory.changed_at)
        .where(
            TicketStatusHistory.ticket_id == ticket_id,
            TicketStatusHistory.new_status == "on_hold",
        )
        .order_by(TicketStatusHistory.changed_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def transition(
    session: AsyncSession,
    ticket: Ticket,
    new_status: str,
    actor_id: uuid.UUID | None,
    actor_role: str | None,
) -> None:
    """Validate against §10, apply SLA timer effects, write both trail tables.

    `actor_role=None` means the system itself (automatic transitions).
    """
    old = ticket.status
    allowed_roles = TRANSITIONS.get((old, new_status))
    if allowed_roles is None:
        raise HTTPException(
            status_code=409, detail=f"Illegal status transition: {old} -> {new_status}"
        )
    if actor_role is not None and actor_role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Role may not perform this transition")

    now = _now()
    if (old, new_status) == ("on_hold", "in_progress"):
        hold_start = await _hold_started_at(session, ticket.id)
        if hold_start:
            timers.resume_after_hold(ticket, hold_start, now)
    elif new_status == "resolved":
        ticket.resolved_at = now
    elif new_status == "closed":
        ticket.closed_at = now
    elif new_status == "reopened":
        ticket.reopened_count += 1
        ticket.resolved_at = None
        ticket.closed_at = None
        # Fresh segment, never the original clock (App Flow Doc 03 §10/§16)
        await timers.fresh_resolution_segment(session, ticket, now)

    ticket.status = new_status
    ticket.updated_at = now
    _record(session, ticket, old, new_status, actor_id)


def record_merged(session: AsyncSession, ticket: Ticket, actor_id: uuid.UUID | None) -> None:
    """Merge closes the secondary as the documented 'Merged' variant of Closed
    (App Flow Doc 03 §20) — the one status write that bypasses the §10 table."""
    old = ticket.status
    now = _now()
    ticket.status = "closed"
    ticket.closed_at = now
    ticket.updated_at = now
    _record(session, ticket, old, "closed", actor_id, action="merged")
