"""LangGraph AI pipeline (TRD §5; Implementation Plan Phase 5).

Graph: redact → embed → retrieve → classify → [confidence branch §14]
  high   → route (apply class + routing agent + assignment) → draft
  medium → draft (suggestion only; agent confirms via the API before routing)
  low    → END (manual classification required; nothing pre-filled)

The Draft Response Agent only ever writes ai_draft_history rows — never
comments. Human review happens at the API (app/ai/service.py).
"""

import asyncio
import logging
import uuid
from typing import Any, TypedDict

import sqlalchemy as sa
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import classifier, gemini, pii
from app.config import get_settings
from app.models import (
    AiClassificationHistory,
    AiDraftHistory,
    Category,
    Embedding,
    KnowledgeBaseArticle,
    Priority,
    Ticket,
)
from app.routing import service as routing
from app.sla import timers

logger = logging.getLogger("agentdesk")

MODEL_VERSION = "gemini-2.5-flash+distilbert-seed-v1"

_CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "priority": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["category", "priority", "confidence"],
}


class PipelineState(TypedDict, total=False):
    session: Any  # AsyncSession — carried through the graph, never serialized
    ticket: Any  # Ticket ORM row
    redacted: str
    vector: list[float]
    similar: list[dict]  # prior tickets from pgvector search
    articles: list[dict]  # published KB articles
    categories: dict[str, uuid.UUID]  # name → id (the taxonomy)
    priorities: dict[str, uuid.UUID]
    category_id: uuid.UUID | None
    priority_id: uuid.UUID | None
    confidence: float
    tier: str


# --- Nodes ---


async def _redact(state: PipelineState) -> dict:
    ticket: Ticket = state["ticket"]
    return {"redacted": pii.redact(f"{ticket.subject}\n{ticket.description}")}


async def _embed(state: PipelineState) -> dict:
    session: AsyncSession = state["session"]
    ticket: Ticket = state["ticket"]
    vector = await gemini.embed(state["redacted"])
    existing = (
        await session.execute(sa.select(Embedding).where(Embedding.ticket_id == ticket.id))
    ).scalar_one_or_none()
    if existing:
        existing.embedding = vector
        existing.source_model = get_settings().gemini_embedding_model
    else:
        session.add(
            Embedding(
                ticket_id=ticket.id,
                source_model=get_settings().gemini_embedding_model,
                embedding=vector,
            )
        )
    await session.flush()
    return {"vector": vector}


async def _retrieve(state: PipelineState) -> dict:
    """Hybrid retrieval: the taxonomy tree + pgvector similarity over prior
    tickets and published KB articles (TRD §5 stage 5)."""
    session: AsyncSession = state["session"]
    ticket: Ticket = state["ticket"]
    vector = state["vector"]

    categories = {c.name: c.id for c in (await session.execute(sa.select(Category))).scalars()}
    priorities = {p.name: p.id for p in (await session.execute(sa.select(Priority))).scalars()}

    similar_rows = await session.execute(
        sa.select(Ticket.subject, Ticket.category_id, Ticket.status)
        .join(Embedding, Embedding.ticket_id == Ticket.id)
        .where(Ticket.id != ticket.id)
        .order_by(Embedding.embedding.cosine_distance(vector))
        .limit(5)
    )
    category_names = {v: k for k, v in categories.items()}
    similar = [
        {"subject": s, "category": category_names.get(c), "status": st} for s, c, st in similar_rows
    ]

    article_rows = await session.execute(
        sa.select(KnowledgeBaseArticle.title, KnowledgeBaseArticle.body)
        .where(
            KnowledgeBaseArticle.status == "published",
            KnowledgeBaseArticle.embedding.is_not(None),
        )
        .order_by(KnowledgeBaseArticle.embedding.cosine_distance(vector))
        .limit(3)
    )
    articles = [{"title": t, "body": b[:1500]} for t, b in article_rows]
    return {
        "similar": similar,
        "articles": articles,
        "categories": categories,
        "priorities": priorities,
    }


def _taxonomy_lines(categories: dict[str, uuid.UUID]) -> str:
    return "\n".join(f"- {name}" for name in sorted(categories))


async def _classify(state: PipelineState) -> dict:
    """Hybrid classification: LLM reasoning pass blended with the DistilBERT
    prediction, recorded in ai_classification_history (TRD §5 stages 6–7)."""
    session: AsyncSession = state["session"]
    ticket: Ticket = state["ticket"]
    settings = get_settings()

    similar_text = (
        "\n".join(f"- {s['subject']} (category: {s['category']})" for s in state["similar"])
        or "(none)"
    )
    prompt = (
        "You are the ticket classifier for a helpdesk. Pick exactly one category and one "
        "priority from the lists below for the ticket, with a confidence from 0 to 100.\n\n"
        f"Categories:\n{_taxonomy_lines(state['categories'])}\n\n"
        f"Priorities: {', '.join(sorted(state['priorities']))}\n\n"
        f"Similar past tickets:\n{similar_text}\n\n"
        f"Ticket:\n{state['redacted']}"
    )
    llm = await gemini.generate_json(prompt, _CLASSIFY_SCHEMA)
    llm_category = llm.get("category")
    llm_confidence = max(0.0, min(100.0, float(llm.get("confidence", 0))))

    bert = await asyncio.to_thread(classifier.predict, state["redacted"])
    category_name, confidence = llm_category, llm_confidence
    if bert is not None:
        bert_category, bert_prob = bert
        if bert_category == llm_category:
            # ponytail: fixed 60/40 blend on agreement, dampen on disagreement —
            # recalibrate against real data (App Flow §14 flags thresholds too)
            confidence = 0.6 * llm_confidence + 0.4 * bert_prob * 100
        else:
            confidence = 0.6 * llm_confidence

    category_id = state["categories"].get(category_name)
    priority_id = state["priorities"].get(llm.get("priority"))
    if confidence >= settings.ai_confidence_high:
        tier = "high"
    elif confidence >= settings.ai_confidence_medium:
        tier = "medium"
    else:
        tier = "low"
    if category_id is None:  # LLM produced an unknown label — never auto-act on it
        tier = "low"

    session.add(
        AiClassificationHistory(
            ticket_id=ticket.id,
            predicted_category_id=category_id,
            predicted_priority_id=priority_id,
            confidence=round(confidence, 2),
            confidence_tier=tier,
            model_version=MODEL_VERSION,
        )
    )
    await session.flush()
    return {
        "category_id": category_id,
        "priority_id": priority_id,
        "confidence": round(confidence, 2),
        "tier": tier,
    }


async def _route(state: PipelineState) -> dict:
    """High confidence only: apply the prediction and hand off to the Routing
    Agent (§14 auto-route)."""
    session: AsyncSession = state["session"]
    ticket: Ticket = state["ticket"]
    ticket.category_id = state["category_id"]
    if state.get("priority_id"):
        ticket.priority_id = state["priority_id"]
    # First classification starts the SLA clocks, anchored at creation (§16)
    await timers.start_timers(session, ticket, ticket.created_at)
    await routing.route_and_assign(session, ticket)
    return {}


async def _draft(state: PipelineState) -> dict:
    """Draft Response Agent — writes ai_draft_history only, never comments."""
    session: AsyncSession = state["session"]
    ticket: Ticket = state["ticket"]
    articles_text = (
        "\n\n".join(f"## {a['title']}\n{a['body']}" for a in state["articles"])
        or "(no knowledge base articles available)"
    )
    prompt = (
        "You are a helpdesk agent. Draft a reply to the customer ticket below. Be concise, "
        "empathetic, and concrete. Ground the answer in the knowledge base articles when "
        "relevant; do not invent policies. Reply with the message body only.\n\n"
        f"Knowledge base:\n{articles_text}\n\n"
        f"Ticket:\n{state['redacted']}"
    )
    content = await gemini.generate_text(prompt)
    session.add(
        AiDraftHistory(
            ticket_id=ticket.id,
            generated_by_model=get_settings().gemini_model,
            draft_content=content.strip(),
            confidence_score=state.get("confidence"),
        )
    )
    await session.flush()
    return {}


def _branch(state: PipelineState) -> str:
    return state["tier"]


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("redact", _redact)
    graph.add_node("embed", _embed)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("classify", _classify)
    graph.add_node("route", _route)
    graph.add_node("draft", _draft)
    graph.set_entry_point("redact")
    graph.add_edge("redact", "embed")
    graph.add_edge("embed", "retrieve")
    graph.add_edge("retrieve", "classify")
    # App Flow §14: high → auto-route; medium → suggest (draft only); low → manual
    graph.add_conditional_edges(
        "classify", _branch, {"high": "route", "medium": "draft", "low": END}
    )
    graph.add_edge("route", "draft")
    graph.add_edge("draft", END)
    return graph.compile()


_graph = build_graph()


async def run(session: AsyncSession, ticket: Ticket) -> None:
    await _graph.ainvoke({"session": session, "ticket": ticket})


async def run_for_ticket(ticket_id: uuid.UUID) -> None:
    """Background entry point (TRD §11) — own session, never raises into the
    request path, no-ops without an API key so ticket creation always works."""
    if not get_settings().gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — AI pipeline skipped for ticket %s", ticket_id)
        return
    from app.db import _session_factory

    async with _session_factory() as session:
        try:
            ticket = await session.get(Ticket, ticket_id)
            if ticket is None:
                return
            await run(session, ticket)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("AI pipeline failed for ticket %s", ticket_id)
