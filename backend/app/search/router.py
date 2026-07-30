"""Search + saved views (Phase 8; TRD §6, App Flow §18).

`GET /search/tickets` is a thin handler over the hybrid search service.
`/saved-views` is per-user CRUD over stored filter sets — every row is scoped to
its owner, so no cross-user access is possible.
"""

import uuid
from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from app.auth.deps import CurrentUser, SessionDep, role_name
from app.models import SavedView
from app.search import service
from app.validators import BoundedJson, SafeText

router = APIRouter(tags=["search"])


class TicketHit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_id: int | None
    subject: str
    status: str
    priority_id: uuid.UUID | None
    category_id: uuid.UUID | None
    assignee_id: uuid.UUID | None
    created_at: datetime


class KbHit(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    category_id: uuid.UUID | None


class SearchResults(BaseModel):
    query: str
    tickets: list[dict]
    kb_articles: list[dict]


@router.get("/search/tickets")
async def search(
    caller: CurrentUser,
    session: SessionDep,
    q: Annotated[SafeText, Query(min_length=1)],
    status: str | None = None,
    priority_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    queue_id: uuid.UUID | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SearchResults:
    role = await role_name(session, caller.role_id)
    filters = {
        "status": status,
        "priority_id": priority_id,
        "category_id": category_id,
        "assignee_id": assignee_id,
        "queue_id": queue_id,
        "created_after": created_after,
        "created_before": created_before,
    }
    qvec = await service.embed_query(q)
    ticket_hits = await service.search_tickets(
        session, caller, role, q, filters, qvec, limit, offset
    )
    kb_hits = await service.search_kb(session, role, q, qvec, limit)
    return SearchResults(
        query=q,
        tickets=[
            {"score": h["score"], **TicketHit.model_validate(h["ticket"]).model_dump(mode="json")}
            for h in ticket_hits
        ],
        kb_articles=[
            {"score": h["score"], **KbHit.model_validate(h["article"]).model_dump(mode="json")}
            for h in kb_hits
        ],
    )


# --- Saved views (per-user CRUD) ---


class SavedViewIn(BaseModel):
    name: SafeText
    filters: BoundedJson


class SavedViewPatch(BaseModel):
    name: SafeText | None = None
    filters: BoundedJson | None = None


class SavedViewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    filters: dict
    created_at: datetime


@router.get("/saved-views")
async def list_saved_views(caller: CurrentUser, session: SessionDep) -> list[SavedViewOut]:
    result = await session.execute(
        sa.select(SavedView)
        .where(SavedView.user_id == caller.id)
        .order_by(SavedView.created_at.desc())
    )
    return [SavedViewOut.model_validate(v) for v in result.scalars()]


@router.post("/saved-views", status_code=201)
async def create_saved_view(
    body: SavedViewIn, caller: CurrentUser, session: SessionDep
) -> SavedViewOut:
    view = SavedView(user_id=caller.id, name=body.name, filters=body.filters)
    session.add(view)
    await session.commit()
    return SavedViewOut.model_validate(view)


async def _own_view(session: SessionDep, caller: CurrentUser, view_id: uuid.UUID) -> SavedView:
    view = await session.get(SavedView, view_id)
    if view is None or view.user_id != caller.id:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return view


@router.patch("/saved-views/{view_id}")
async def update_saved_view(
    view_id: uuid.UUID, body: SavedViewPatch, caller: CurrentUser, session: SessionDep
) -> SavedViewOut:
    view = await _own_view(session, caller, view_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(view, key, value)
    await session.commit()
    return SavedViewOut.model_validate(view)


@router.delete("/saved-views/{view_id}", status_code=204)
async def delete_saved_view(
    view_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> Response:
    view = await _own_view(session, caller, view_id)
    await session.delete(view)
    await session.commit()
    return Response(status_code=204)
