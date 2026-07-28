"""Hybrid search (Phase 8; TRD §6, App Flow §18).

One SQL pass blends Postgres FTS, pg_trgm fuzzy matching, and pgvector cosine
similarity over tickets, with metadata filters applied in the WHERE clause
before ranking. Row visibility reuses `scope_tickets_to_caller` (Doc 05 §6), so
the same query is correctly scoped per role. Knowledge Base results ride along
in the same response, scoped by role (requester → published only; staff/admin →
drafts too), per §18.
"""

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gemini
from app.auth.deps import scope_tickets_to_caller
from app.models import Comment, Embedding, KnowledgeBaseArticle, Queue, Tag, Ticket, TicketTag, User

# Trigram floor below which a fuzzy subject match is noise, and the cosine
# distance above which a vector neighbour is unrelated. ponytail: constants
# until real relevance data says otherwise (TRD §6 flags weights as tunable).
_TRGM_FLOOR = 0.1
_VEC_CEILING = 0.5


async def embed_query(q: str) -> list[float] | None:
    """Embed the query for the vector term; None (skip vector) if AI is unavailable."""
    try:
        return await gemini.embed(q)
    except Exception:
        # No GEMINI_API_KEY or a transient API error → degrade to FTS + trigram only.
        return None


def _ticket_fts_match(q: str):
    # Matches migration 0001's GIN index expression exactly so the index is used.
    return sa.text(
        "to_tsvector('english', tickets.subject || ' ' || tickets.description) "
        "@@ plainto_tsquery('english', :q)"
    ).bindparams(q=q)


def _ticket_fts_rank(q: str):
    return sa.func.ts_rank(
        sa.text("to_tsvector('english', tickets.subject || ' ' || tickets.description)"),
        sa.func.plainto_tsquery("english", q),
    )


async def search_tickets(
    session: AsyncSession,
    caller: User,
    role: str,
    q: str,
    filters: dict,
    qvec: list[float] | None,
    limit: int,
    offset: int,
) -> list[dict]:
    scope = scope_tickets_to_caller(caller, role, Ticket, Queue, User)
    trgm = sa.func.similarity(Ticket.subject, q)

    # Vector term via a left join on embeddings; missing embedding → distance 1 (no signal).
    vec_dist = sa.func.coalesce(Embedding.embedding.cosine_distance(qvec), 1.0) if qvec else None

    # Comment-body match, respecting internal-note visibility for requesters.
    comment_q = sa.select(Comment.id).where(
        Comment.ticket_id == Ticket.id,
        sa.text(
            "to_tsvector('english', comments.body) @@ plainto_tsquery('english', :cq)"
        ).bindparams(cq=q),
    )
    if role == "requester":
        comment_q = comment_q.where(Comment.is_internal.is_(False))
    tag_q = (
        sa.select(TicketTag.ticket_id)
        .join(Tag, Tag.id == TicketTag.tag_id)
        .where(TicketTag.ticket_id == Ticket.id, sa.func.similarity(Tag.name, q) > 0.3)
    )

    match_terms = [_ticket_fts_match(q), trgm > _TRGM_FLOOR, comment_q.exists(), tag_q.exists()]
    if qvec:
        match_terms.append(vec_dist < _VEC_CEILING)

    score = (2 * _ticket_fts_rank(q)) + trgm + ((1 - vec_dist) if qvec else 0)

    query = (
        sa.select(Ticket, score.label("score"))
        .where(scope, sa.or_(*match_terms))
        .order_by(sa.desc("score"), Ticket.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if qvec:
        query = query.outerjoin(Embedding, Embedding.ticket_id == Ticket.id)

    for field in ("status", "priority_id", "category_id", "assignee_id", "queue_id"):
        if filters.get(field) is not None:
            query = query.where(getattr(Ticket, field) == filters[field])
    if filters.get("created_after"):
        query = query.where(Ticket.created_at >= filters["created_after"])
    if filters.get("created_before"):
        query = query.where(Ticket.created_at <= filters["created_before"])

    rows = (await session.execute(query)).all()
    return [{"ticket": ticket, "score": round(float(sc), 4)} for ticket, sc in rows]


async def search_kb(
    session: AsyncSession, role: str, q: str, qvec: list[float] | None, limit: int
) -> list[dict]:
    kb_tsv = sa.text(
        "to_tsvector('english', knowledge_base_articles.title || ' ' || "
        "knowledge_base_articles.body)"
    )
    fts_rank = sa.func.ts_rank(kb_tsv, sa.func.plainto_tsquery("english", q))
    fts_match = sa.text(
        "to_tsvector('english', knowledge_base_articles.title || ' ' || "
        "knowledge_base_articles.body) @@ plainto_tsquery('english', :kq)"
    ).bindparams(kq=q)
    trgm = sa.func.similarity(KnowledgeBaseArticle.title, q)
    vec_dist = (
        sa.func.coalesce(KnowledgeBaseArticle.embedding.cosine_distance(qvec), 1.0)
        if qvec
        else None
    )

    match_terms = [fts_match, trgm > _TRGM_FLOOR]
    if qvec:
        match_terms.append(vec_dist < _VEC_CEILING)
    score = (2 * fts_rank) + trgm + ((1 - vec_dist) if qvec else 0)

    query = sa.select(KnowledgeBaseArticle, score.label("score")).where(sa.or_(*match_terms))
    if role == "requester":  # §18: requesters see published articles only
        query = query.where(KnowledgeBaseArticle.status == "published")
    query = query.order_by(sa.desc("score")).limit(limit)

    rows = (await session.execute(query)).all()
    return [{"article": art, "score": round(float(sc), 4)} for art, sc in rows]
