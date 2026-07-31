"""Knowledge base read API (TRD §3; RBAC per Document 05 §6)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from app.auth.deps import CurrentUser, SessionDep, role_name
from app.knowledge_base import service
from app.validators import SafeText

router = APIRouter(prefix="/knowledge-base", tags=["knowledge base"])


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
