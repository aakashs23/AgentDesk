"""Backfill embeddings for published KB articles that have none.

Publishing through the API embeds the article (App Flow §19 steps 5–6), so this
only matters for rows that arrived another way — the seed script's demo
articles, or anything published while `GEMINI_API_KEY` was unset. Without a
vector an article is still findable by full-text search, but the AI pipeline's
retrieval node skips it, so it is never suggested on a new ticket.

    python -m scripts.reindex_kb        # from backend/, idempotent
"""

import asyncio

import sqlalchemy as sa

from app.config import get_settings
from app.db import _session_factory
from app.knowledge_base.service import embed_article
from app.models import KnowledgeBaseArticle


async def main() -> None:
    if not get_settings().gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is not set — nothing to embed with.")
    async with _session_factory() as session:
        articles = list(
            (
                await session.execute(
                    sa.select(KnowledgeBaseArticle).where(
                        KnowledgeBaseArticle.status == "published",
                        KnowledgeBaseArticle.embedding.is_(None),
                    )
                )
            ).scalars()
        )
        for article in articles:
            await embed_article(article)
            print(f"embedded: {article.title}")
        await session.commit()
    print(f"{len(articles)} article(s) reindexed.")


if __name__ == "__main__":
    asyncio.run(main())
