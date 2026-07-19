"""AI endpoints (TRD §3 + Phase 5): insights, human-in-the-loop draft review,
and the §14 confirm/correct classification loop. Staff-only — thin handlers."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai import schemas, service
from app.auth.deps import SessionDep, require_role, role_name
from app.models import User
from app.tickets.schemas import TicketOut

router = APIRouter(tags=["ai"])

StaffUser = Annotated[User, Depends(require_role("agent", "team_lead", "admin"))]


@router.get("/tickets/{ticket_id}/ai")
async def get_insights(
    ticket_id: uuid.UUID, caller: StaffUser, session: SessionDep
) -> schemas.InsightsOut:
    role = await role_name(session, caller.role_id)
    classification, drafts = await service.get_insights(session, caller, role, ticket_id)
    return schemas.InsightsOut(
        classification=schemas.ClassificationOut.model_validate(classification)
        if classification
        else None,
        drafts=[schemas.DraftOut.model_validate(d) for d in drafts],
    )


@router.post("/ai/drafts/{draft_id}/review")
async def review_draft(
    draft_id: uuid.UUID, body: schemas.DraftReview, caller: StaffUser, session: SessionDep
) -> schemas.DraftOut:
    role = await role_name(session, caller.role_id)
    draft = await service.review_draft(session, caller, role, draft_id, body.action, body.content)
    return schemas.DraftOut.model_validate(draft)


@router.post("/tickets/{ticket_id}/classification/confirm")
async def confirm_classification(
    ticket_id: uuid.UUID, caller: StaffUser, session: SessionDep
) -> TicketOut:
    role = await role_name(session, caller.role_id)
    return TicketOut.model_validate(
        await service.confirm_classification(session, caller, role, ticket_id)
    )


@router.post("/tickets/{ticket_id}/classification/correct")
async def correct_classification(
    ticket_id: uuid.UUID,
    body: schemas.ClassificationCorrection,
    caller: StaffUser,
    session: SessionDep,
) -> TicketOut:
    role = await role_name(session, caller.role_id)
    return TicketOut.model_validate(
        await service.correct_classification(
            session, caller, role, ticket_id, body.category_id, body.priority_id
        )
    )
