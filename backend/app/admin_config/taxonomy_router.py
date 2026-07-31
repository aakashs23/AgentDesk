"""Read-only taxonomy endpoints (categories, priorities).

Document 05 §6 makes categories/priorities/queues read-only for every non-admin
role "where exposed (e.g. category dropdown on the ticket form)" — which is
exactly what the Customer Portal's New Ticket form needs. Admin write access
lives in the `/admin` router, not here.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.auth.deps import CurrentUser, SessionDep
from app.models import Category, Priority

router = APIRouter(tags=["taxonomy"])


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    created_at: datetime


class PriorityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    rank: int
    color_hex: str
    created_at: datetime


@router.get("/categories")
async def list_categories(_: CurrentUser, session: SessionDep) -> list[CategoryOut]:
    """The full adjacency-list tree, flat. The taxonomy is small enough that the
    client can nest it by `parent_id` without a recursive query."""
    query = sa.select(Category).order_by(Category.name)
    return [CategoryOut.model_validate(c) for c in (await session.execute(query)).scalars()]


@router.get("/priorities")
async def list_priorities(_: CurrentUser, session: SessionDep) -> list[PriorityOut]:
    # Ascending rank: lower = less urgent (Doc 05, priorities table).
    query = sa.select(Priority).order_by(Priority.rank)
    return [PriorityOut.model_validate(p) for p in (await session.execute(query)).scalars()]
