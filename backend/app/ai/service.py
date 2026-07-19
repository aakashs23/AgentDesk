"""Human-in-the-loop AI operations (Implementation Plan Phase 5).

Draft review (approve/edit/reject), the §14 medium-tier confirm, and the
correction feedback loop. All mandatory-human-review rules live here: a draft
becomes a comment only through review_draft, and a rejected draft never does.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.models import AiClassificationHistory, AiDraftHistory, Category, Comment, Priority, User
from app.routing import service as routing
from app.sla import timers
from app.tickets.service import _get_or_422, get_ticket_scoped
from app.workflow import engine


def _now() -> datetime:
    return datetime.now(UTC)


async def _latest_classification(
    session: AsyncSession, ticket_id: uuid.UUID
) -> AiClassificationHistory | None:
    result = await session.execute(
        sa.select(AiClassificationHistory)
        .where(AiClassificationHistory.ticket_id == ticket_id)
        .order_by(AiClassificationHistory.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_insights(session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID):
    await get_ticket_scoped(session, caller, role, ticket_id)
    classification = await _latest_classification(session, ticket_id)
    drafts = list(
        (
            await session.execute(
                sa.select(AiDraftHistory)
                .where(AiDraftHistory.ticket_id == ticket_id)
                .order_by(AiDraftHistory.created_at)
            )
        ).scalars()
    )
    return classification, drafts


async def review_draft(
    session: AsyncSession,
    caller: User,
    role: str,
    draft_id: uuid.UUID,
    action: str,
    content: str | None,
) -> AiDraftHistory:
    draft = await session.get(AiDraftHistory, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    ticket = await get_ticket_scoped(session, caller, role, draft.ticket_id)
    if draft.review_status != "pending":
        raise HTTPException(status_code=409, detail="Draft has already been reviewed")
    if action == "edited" and not content:
        raise HTTPException(status_code=422, detail="content is required when editing")

    if action in ("approved", "edited"):
        comment = Comment(
            ticket_id=ticket.id,
            author_id=caller.id,
            body=content if action == "edited" else draft.draft_content,
            is_ai_generated=True,
            ai_confidence=draft.confidence_score,
        )
        session.add(comment)
        await session.flush()
        draft.final_comment_id = comment.id
        # Sending the reply is a staff public reply — same §10 side effect as
        # a manual comment (first agent reply stops the response timer by row).
        if ticket.status == "open":
            await engine.transition(session, ticket, "in_progress", caller.id, role)
    # rejected: final_comment_id stays null, permanently

    draft.review_status = action
    draft.reviewed_by = caller.id
    draft.reviewed_at = _now()
    audit.log(
        session,
        "ai_draft",
        draft.id,
        caller.id,
        f"draft_{action}",
        after={"ticket_id": str(ticket.id), "final_comment_id": str(draft.final_comment_id)},
    )
    await session.commit()
    return draft


async def _apply_and_route(
    session: AsyncSession,
    caller: User,
    ticket,
    category_id: uuid.UUID | None,
    priority_id: uuid.UUID | None,
) -> None:
    before = {"category_id": str(ticket.category_id), "priority_id": str(ticket.priority_id)}
    if category_id:
        ticket.category_id = category_id
    if priority_id:
        ticket.priority_id = priority_id
    ticket.updated_at = _now()
    await timers.start_timers(session, ticket, ticket.created_at)
    audit.log(
        session,
        "ticket",
        ticket.id,
        caller.id,
        "classified",
        before=before,
        after={"category_id": str(ticket.category_id), "priority_id": str(ticket.priority_id)},
    )
    # §14: routing finalizes once an agent confirms/corrects
    await routing.route_and_assign(session, ticket)


async def confirm_classification(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
):
    """Medium tier: the agent accepts the AI suggestion as-is (App Flow §14)."""
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    classification = await _latest_classification(session, ticket_id)
    if classification is None or classification.predicted_category_id is None:
        raise HTTPException(status_code=409, detail="No AI suggestion to confirm")
    await _apply_and_route(
        session,
        caller,
        ticket,
        classification.predicted_category_id,
        classification.predicted_priority_id,
    )
    await session.commit()
    return ticket


async def correct_classification(
    session: AsyncSession,
    caller: User,
    role: str,
    ticket_id: uuid.UUID,
    category_id: uuid.UUID | None,
    priority_id: uuid.UUID | None,
):
    """Agent correction — applied to the ticket and stored as training feedback
    on the classification record (corrected_*, was_overridden)."""
    if category_id is None and priority_id is None:
        raise HTTPException(status_code=422, detail="Provide category_id and/or priority_id")
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    if category_id:
        await _get_or_422(session, Category, category_id, "category")
    if priority_id:
        await _get_or_422(session, Priority, priority_id, "priority")

    classification = await _latest_classification(session, ticket_id)
    if classification is not None:
        classification.was_overridden = True
        classification.overridden_by = caller.id
        classification.corrected_category_id = category_id
        classification.corrected_priority_id = priority_id

    await _apply_and_route(session, caller, ticket, category_id, priority_id)
    await session.commit()
    return ticket
