"""Knowledge base reads, scoped per Document 05 §6.

| Role       | May read                                  |
|------------|-------------------------------------------|
| requester  | `published` only                          |
| agent      | `published` + drafts they authored        |
| team_lead  | `published` + drafts they authored        |
| admin      | everything                                |

Writes follow App Flow §19's creation loop: staff draft an article from a
resolved ticket, only an Admin publishes it. Full admin CRUD is Phase 12.
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
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


# --- Writes (App Flow §19) ---


def _check_publish_rights(role: str, status: str | None) -> None:
    """§19 step 4–5: drafting is a staff action, publishing is an Admin one."""
    if status == "published" and role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin may publish an article")


async def create_article(
    session: AsyncSession,
    user: User,
    role: str,
    title: str,
    body: str,
    category_id: uuid.UUID | None,
    source_ticket_id: uuid.UUID | None,
    status: str,
) -> KnowledgeBaseArticle:
    _check_publish_rights(role, status)
    article = KnowledgeBaseArticle(
        title=title,
        body=body,
        category_id=category_id,
        source_ticket_id=source_ticket_id,
        author_id=user.id,
        status=status,
        published_at=datetime.now(UTC) if status == "published" else None,
    )
    session.add(article)
    await session.flush()
    audit.log(
        session,
        "knowledge_base_article",
        article.id,
        user.id,
        "created",
        after={"title": title, "status": status},
    )
    await session.commit()
    await session.refresh(article)
    return article


async def delete_article(session: AsyncSession, user: User, article_id: uuid.UUID) -> None:
    """Admin-only hard delete (Phase 12). Nothing has an FK onto
    `knowledge_base_articles` — the embedding is a column on the row itself — so
    there is nothing to orphan, and the audit row survives the article."""
    article = await session.get(KnowledgeBaseArticle, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    audit.log(
        session,
        "knowledge_base_article",
        article.id,
        user.id,
        "deleted",
        before={"title": article.title, "status": article.status},
    )
    await session.delete(article)
    await session.commit()


async def update_article(
    session: AsyncSession, user: User, role: str, article_id: uuid.UUID, changes: dict
) -> KnowledgeBaseArticle:
    article = await get_article_scoped(session, user, role, article_id)
    if role != "admin" and article.author_id != user.id:
        raise HTTPException(status_code=403, detail="Not the article author")
    _check_publish_rights(role, changes.get("status"))

    before = {k: getattr(article, k) for k in changes}
    for key, value in changes.items():
        setattr(article, key, value)
    if changes.get("status") == "published" and article.published_at is None:
        article.published_at = datetime.now(UTC)
    article.updated_at = datetime.now(UTC)
    audit.log(
        session,
        "knowledge_base_article",
        article.id,
        user.id,
        "updated",
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    await session.refresh(article)
    return article
