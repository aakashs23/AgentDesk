"""Knowledge base reads, scoped per Document 05 §6.

| Role       | May read                                  |
|------------|-------------------------------------------|
| requester  | `published` only                          |
| agent      | `published` + drafts they authored        |
| team_lead  | `published` + drafts they authored        |
| admin      | everything                                |

Writes follow App Flow §19's creation loop: staff draft an article from a
resolved ticket, only an Admin publishes it. Full admin CRUD is Phase 12.

Publishing embeds the article (§19 steps 5–6): the AI pipeline's retrieval node
and the vector half of search both match on `knowledge_base_articles.embedding`,
so an article without one is invisible to suggestions no matter what it says.
"""

import logging
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gemini, pii
from app.audit import service as audit
from app.models import KnowledgeBaseArticle, User
from app.search import service as search

logger = logging.getLogger("agentdesk")


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
    status: str | None = None,
) -> list[KnowledgeBaseArticle]:
    criteria = [scope_articles_to_caller(user, role)]
    if category_id is not None:
        criteria.append(KnowledgeBaseArticle.category_id == category_id)
    if status is not None:
        criteria.append(KnowledgeBaseArticle.status == status)

    if q:
        # Same matcher as global search and the chat widget, so the New Ticket
        # form's suggestions rank a paraphrase the way §19 step 6 expects rather
        # than needing a literal substring. It degrades to FTS + trigram with no
        # GEMINI_API_KEY, so browsing never depends on the AI provider.
        hits = await search.search_kb(
            session, sa.and_(*criteria), q, await search.embed_query(q), limit, offset
        )
        return [hit["article"] for hit in hits]

    query = (
        sa.select(KnowledgeBaseArticle)
        .where(*criteria)
        .order_by(KnowledgeBaseArticle.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )
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


async def embed_article(article: KnowledgeBaseArticle) -> None:
    """Give a published article the vector the suggestion path matches on.

    Title + body, redacted, one vector on the row — deliberately produced the
    same way as a ticket's (subject + description → `pii.redact` →
    `gemini.embed`), because the pipeline compares the two directly with
    `cosine_distance` and only vectors from the same text pipeline are
    comparable.

    Never fatal: publishing must still succeed with no GEMINI_API_KEY or a
    provider outage. The article is then findable by FTS/trigram and gets its
    vector on the next edit (or via `scripts/reindex_kb.py`).
    """
    try:
        article.embedding = await gemini.embed(pii.redact(f"{article.title}\n{article.body}"))
    except Exception:
        logger.exception("KB embedding failed for article %s — published without one", article.id)


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
    if status == "published":
        await embed_article(article)
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
    # Re-embed whenever a published article's text changes, or the first time it
    # is published: a stale vector suggests the article on the wrong tickets.
    if article.status == "published" and (
        article.embedding is None or {"title", "body"} & changes.keys()
    ):
        await embed_article(article)
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
