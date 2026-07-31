"""Knowledge base reads, scoped per Document 05 §6.

| Role       | May read                                  |
|------------|-------------------------------------------|
| requester  | `published` only                          |
| agent      | `published` + drafts they authored        |
| team_lead  | `published` + drafts they authored        |
| admin      | everything                                |

Write access (create/edit from a resolved ticket) is Phase 11/12 work — this
module ships the read side the Customer Portal needs.
"""

import uuid

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBaseArticle, User


def scope_articles_to_caller(user: User, role: str):
    """Boolean criterion limiting a KB query to what the caller may see.

    Mirrors `scope_tickets_to_caller` so article visibility has exactly one
    definition, rather than being re-derived per endpoint.
    """
    if role == "admin":
        return sa.true()
    published = KnowledgeBaseArticle.status == "published"
    if role == "requester":
        return published
    # Staff additionally see their own drafts.
    return sa.or_(published, KnowledgeBaseArticle.author_id == user.id)


async def list_articles(
    session: AsyncSession,
    user: User,
    role: str,
    q: str | None,
    category_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> list[KnowledgeBaseArticle]:
    query = sa.select(KnowledgeBaseArticle).where(scope_articles_to_caller(user, role))
    if q:
        # Plain ILIKE, not the hybrid vector search in `app.search`: browsing the
        # KB is a title/body substring match, and it must work with no
        # GEMINI_API_KEY configured. `/search/tickets` covers semantic recall.
        pattern = f"%{q}%"
        query = query.where(
            sa.or_(
                KnowledgeBaseArticle.title.ilike(pattern),
                KnowledgeBaseArticle.body.ilike(pattern),
            )
        )
    if category_id is not None:
        query = query.where(KnowledgeBaseArticle.category_id == category_id)
    query = query.order_by(KnowledgeBaseArticle.updated_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(query)).scalars())


async def get_article_scoped(
    session: AsyncSession, user: User, role: str, article_id: uuid.UUID
) -> KnowledgeBaseArticle:
    query = sa.select(KnowledgeBaseArticle).where(
        KnowledgeBaseArticle.id == article_id, scope_articles_to_caller(user, role)
    )
    article = (await session.execute(query)).scalar_one_or_none()
    if article is None:
        # 404 rather than 403: an unpublished draft should not be discoverable.
        raise HTTPException(status_code=404, detail="Article not found")
    return article
