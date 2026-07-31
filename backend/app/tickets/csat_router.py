"""CSAT responses (App Flow Doc 03 §1, §7 — the survey modal shown on the
requester's next visit to a resolved ticket).

Document 05 defines `csat_responses` but no earlier phase read or wrote it;
Phase 10 gives it an API because the Customer Portal's survey needs one.
"""

import uuid
from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import CurrentUser, SessionDep, role_name, scope_tickets_to_caller
from app.models import CsatResponse, Queue, Ticket, User
from app.tickets import service
from app.validators import SafeText

router = APIRouter(tags=["csat"])

# The survey is a post-resolution question, so it only makes sense once the
# ticket has actually reached one of these states (App Flow §10).
SURVEYABLE_STATUSES = {"resolved", "closed"}


class CsatIn(BaseModel):
    ticket_id: uuid.UUID
    rating: Annotated[int, Field(ge=1, le=5)]  # 1–5, per Doc 05's note
    comment: SafeText | None = None


class CsatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    rating: int
    comment: str | None
    submitted_at: datetime


@router.post("/csat", status_code=201)
async def submit_csat(body: CsatIn, caller: CurrentUser, session: SessionDep) -> CsatOut:
    role = await role_name(session, caller.role_id)
    # Reuse the ticket scoping rather than re-deriving visibility: a 404 here
    # means "not your ticket" without leaking that the ticket exists.
    ticket = await service.get_ticket_scoped(session, caller, role, body.ticket_id)

    # Satisfaction is the requester's to report — an agent rating their own work
    # would make the metric meaningless.
    if ticket.requester_id != caller.id:
        raise HTTPException(status_code=403, detail="Only the requester can rate a ticket")
    if ticket.status not in SURVEYABLE_STATUSES:
        raise HTTPException(status_code=409, detail="Ticket is not resolved yet")

    existing = await session.execute(
        sa.select(CsatResponse).where(CsatResponse.ticket_id == body.ticket_id)
    )
    if existing.scalar_one_or_none() is not None:
        # The table enforces this too; catching it here gives a clearer error
        # than a unique-violation surfacing as a 500.
        raise HTTPException(status_code=409, detail="This ticket has already been rated")

    response = CsatResponse(ticket_id=body.ticket_id, rating=body.rating, comment=body.comment)
    session.add(response)
    await session.commit()
    await session.refresh(response)
    return CsatOut.model_validate(response)


@router.get("/csat")
async def list_csat(
    caller: CurrentUser,
    session: SessionDep,
    ticket_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CsatOut]:
    """Responses for tickets the caller can see. The portal passes `ticket_id`
    to decide whether the survey modal still needs showing."""
    role = await role_name(session, caller.role_id)
    visible = scope_tickets_to_caller(caller, role, Ticket, Queue, User)
    query = (
        sa.select(CsatResponse)
        .join(Ticket, Ticket.id == CsatResponse.ticket_id)
        .where(visible)
        .order_by(CsatResponse.submitted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if ticket_id is not None:
        query = query.where(CsatResponse.ticket_id == ticket_id)
    return [CsatOut.model_validate(r) for r in (await session.execute(query)).scalars()]
