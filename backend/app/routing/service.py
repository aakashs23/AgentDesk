"""Routing Agent (TRD §5 stage 8) — selects a queue and an assignee.

Rules for the prototype: category-based queue match (queue name == top-level
category name, else the first queue), then load-balanced assignee (active agent
on the queue's team with the fewest open tickets).
"""

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.models import Category, Queue, Role, Ticket, User
from app.workflow import engine

logger = logging.getLogger("agentdesk")

OPEN_STATUSES = ("new", "open", "in_progress", "on_hold", "reopened")


async def _top_level_category_name(session: AsyncSession, category_id: uuid.UUID) -> str | None:
    category = await session.get(Category, category_id)
    while category is not None and category.parent_id is not None:
        category = await session.get(Category, category.parent_id)
    return category.name if category else None


async def _pick_queue(session: AsyncSession, ticket: Ticket) -> Queue | None:
    queues = list((await session.execute(sa.select(Queue))).scalars())
    if not queues:
        return None
    if ticket.category_id:
        root_name = await _top_level_category_name(session, ticket.category_id)
        for queue in queues:
            if root_name and queue.name.lower().startswith(root_name.lower()):
                return queue
    # ponytail: no category→queue mapping table in the schema; name-match or
    # first queue. Revisit when Admin queue management (Phase 9) lands.
    return queues[0]


async def _pick_assignee(session: AsyncSession, queue: Queue) -> User | None:
    open_counts = (
        sa.select(Ticket.assignee_id, sa.func.count().label("n"))
        .where(Ticket.status.in_(OPEN_STATUSES))
        .group_by(Ticket.assignee_id)
        .subquery()
    )
    result = await session.execute(
        sa.select(User)
        .join(Role, Role.id == User.role_id)
        .outerjoin(open_counts, open_counts.c.assignee_id == User.id)
        .where(Role.name == "agent", User.is_active.is_(True), User.team_id == queue.team_id)
        .order_by(sa.func.coalesce(open_counts.c.n, 0))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def route_and_assign(session: AsyncSession, ticket: Ticket) -> None:
    """System routing after a finalized classification. Writes queue + assignee,
    audits as the system actor, and moves New → Open."""
    queue = await _pick_queue(session, ticket)
    if queue is None:
        logger.warning("routing: no queues exist, ticket %s left unrouted", ticket.id)
        return
    before = {"assignee_id": str(ticket.assignee_id), "queue_id": str(ticket.queue_id)}
    ticket.queue_id = queue.id
    assignee = await _pick_assignee(session, queue)
    if assignee:
        ticket.assignee_id = assignee.id
    audit.log(
        session,
        "ticket",
        ticket.id,
        None,  # system actor
        "auto_routed",
        before=before,
        after={"assignee_id": str(ticket.assignee_id), "queue_id": str(ticket.queue_id)},
    )
    if ticket.status == "new":
        await engine.transition(session, ticket, "open", None, None)
