"""Knowledge base read API (TRD §3; RBAC per Document 05 §6)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import CurrentUser, SessionDep, require_role, role_name
from app.knowledge_base import service
from app.models import User
from app.validators import SafeText

router = APIRouter(prefix="/knowledge-base", tags=["knowledge base"])

StaffUser = Annotated[User, Depends(require_role("agent", "team_lead", "admin"))]


class ArticleSummary(BaseModel):
    """List shape — omits `body` so a browse request stays small."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    category_id: uuid.UUID | None
    status: str
    published_at: datetime | None
    updated_at: datetime


class ArticleOut(ArticleSummary):
    body: str
    source_ticket_id: uuid.UUID | None
    author_id: uuid.UUID | None
    created_at: datetime


@router.get("/articles")
async def list_articles(
    caller: CurrentUser,
    session: SessionDep,
    q: Annotated[SafeText | None, Query()] = None,
    category_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ArticleSummary]:
    role = await role_name(session, caller.role_id)
    articles = await service.list_articles(session, caller, role, q, category_id, limit, offset)
    return [ArticleSummary.model_validate(a) for a in articles]


@router.get("/articles/{article_id}")
async def get_article(
    article_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> ArticleOut:
    role = await role_name(session, caller.role_id)
    return ArticleOut.model_validate(
        await service.get_article_scoped(session, caller, role, article_id)
    )


class ArticleCreate(BaseModel):
    title: SafeText = Field(min_length=1, max_length=200)
    body: SafeText = Field(min_length=1, max_length=20_000)
    category_id: uuid.UUID | None = None
    source_ticket_id: uuid.UUID | None = None
    status: Literal["draft", "published"] = "draft"


class ArticleUpdate(BaseModel):
    title: SafeText | None = Field(default=None, min_length=1, max_length=200)
    body: SafeText | None = Field(default=None, min_length=1, max_length=20_000)
    category_id: uuid.UUID | None = None
    status: Literal["draft", "published"] | None = None


@router.post("/articles", status_code=201)
async def create_article(body: ArticleCreate, caller: StaffUser, session: SessionDep) -> ArticleOut:
    role = await role_name(session, caller.role_id)
    return ArticleOut.model_validate(
        await service.create_article(
            session,
            caller,
            role,
            body.title,
            body.body,
            body.category_id,
            body.source_ticket_id,
            body.status,
        )
    )


@router.delete("/articles/{article_id}", status_code=204)
async def delete_article(
    article_id: uuid.UUID,
    caller: Annotated[User, Depends(require_role("admin"))],
    session: SessionDep,
) -> Response:
    """Admin only — Doc 03 §1 gives Admin "full CRUD over KB articles across the
    organization", and an author deleting their own published article would take
    it out from under the suggestion pipeline without review."""
    await service.delete_article(session, caller, article_id)
    return Response(status_code=204)


@router.patch("/articles/{article_id}")
async def update_article(
    article_id: uuid.UUID, body: ArticleUpdate, caller: StaffUser, session: SessionDep
) -> ArticleOut:
    role = await role_name(session, caller.role_id)
    return ArticleOut.model_validate(
        await service.update_article(
            session, caller, role, article_id, body.model_dump(exclude_unset=True)
        )
    )
