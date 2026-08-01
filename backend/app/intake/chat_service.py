"""Chat-widget intake (Implementation Plan Phase 13; App Flow §12).

A conversation lives in `conversation_history` keyed by `session_id` and only
becomes a ticket if self-service fails — that deflection is the point of the
channel (PRD Nice to Have).

**Session ownership** is encoded in the id: `"{user_id}:{uuid4}"`. Doc 05 gives
`conversation_history` no owner column and the schema invariant forbids adding
one, so the id itself carries it — a requester may read and write only sessions
prefixed with their own user id, staff may read any (that is the §12 step 7
takeover). ponytail: swap the prefix check for a real column if the schema ever
gains one.

Article suggestions reuse `search.service.search_kb`, so the widget matches the
same way the New Ticket form does, and still works with no GEMINI_API_KEY (the
full-text and trigram halves need no embedding).
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import gemini
from app.config import get_settings
from app.models import ConversationHistory, KnowledgeBaseArticle, Ticket, User
from app.search import service as search
from app.tickets import schemas
from app.tickets import service as tickets

logger = logging.getLogger("agentdesk.intake")

GREETING = (
    "Hi! I'm the AgentDesk assistant. Tell me what you need help with and I'll "
    "look for an answer — if I can't solve it, I'll turn this into a ticket for you."
)
NO_MATCH = (
    "I couldn't find an article covering that. Tell me a bit more, or ask for a "
    "person and I'll raise a ticket with everything you've said so far."
)
DEFLECTED = "Glad that helped — closing this chat without raising a ticket."
STAFF = ("agent", "team_lead", "admin")
# A session with no ticket and no activity for this long is no longer "live" for
# takeover purposes.
ACTIVE_WINDOW = timedelta(hours=2)


def new_session_id(user: User) -> str:
    return f"{user.id}:{uuid.uuid4()}"


def owns(user: User, role: str, session_id: str) -> bool:
    return role in STAFF or session_id.startswith(f"{user.id}:")


def require_access(user: User, role: str, session_id: str) -> None:
    if not owns(user, role, session_id):
        # 404, not 403: another requester's session must not be discoverable.
        raise HTTPException(status_code=404, detail="Chat session not found")


async def _owner(session: AsyncSession, session_id: str) -> User | None:
    try:
        return await session.get(User, uuid.UUID(session_id.split(":")[0]))
    except ValueError:
        return None


async def transcript(session: AsyncSession, session_id: str) -> list[ConversationHistory]:
    rows = await session.execute(
        sa.select(ConversationHistory)
        .where(ConversationHistory.session_id == session_id)
        .order_by(ConversationHistory.created_at, ConversationHistory.id)
    )
    return list(rows.scalars())


def _say(session: AsyncSession, session_id: str, speaker: str, message: str) -> ConversationHistory:
    row = ConversationHistory(session_id=session_id, speaker=speaker, message=message)
    session.add(row)
    return row


async def start(session: AsyncSession, user: User) -> tuple[str, list[ConversationHistory]]:
    """§12 steps 1–2: open a session and greet."""
    session_id = new_session_id(user)
    _say(session, session_id, "bot", GREETING)
    await session.commit()
    return session_id, await transcript(session, session_id)


async def _suggest(session: AsyncSession, role: str, message: str) -> list[KnowledgeBaseArticle]:
    qvec = await search.embed_query(message)
    hits = await search.search_kb(session, role, message, qvec, limit=3)
    return [hit["article"] for hit in hits]


async def _bot_answer(
    message: str, articles: list[KnowledgeBaseArticle], history: list[ConversationHistory]
) -> str:
    """§12 steps 2–3 is a conversation, not a lookup: an empty knowledge base
    means the bot has nothing to *cite*, not nothing to say. Only the
    no-API-key fallback is canned."""
    if not get_settings().gemini_api_key:
        if not articles:
            return NO_MATCH
        listed = "\n".join(f"- {a.title}" for a in articles)
        return f"These might help:\n{listed}\n\nDid that answer it?"

    grounding = (
        "\n\n".join(f"## {a.title}\n{a.body[:1500]}" for a in articles)
        or "(no matching articles — the knowledge base has nothing on this)"
    )
    # The last few turns, so a follow-up ("it still fails") has its referent.
    recent = "\n".join(f"{row.speaker}: {row.message}" for row in history[-8:]) or "(none)"
    return await gemini.generate_text(
        "You are a helpdesk chat assistant talking to a customer. Ground any factual claim "
        "in the knowledge base articles below and never invent policy. If they do not cover "
        "the issue, do not stonewall: ask one focused clarifying question, or offer to raise "
        "a ticket with what you already have. Two short paragraphs at most, no lists unless "
        "you are citing articles.\n\n"
        f"Knowledge base:\n{grounding}\n\n"
        f"Conversation so far:\n{recent}\n\n"
        f"User: {message}"
    )


async def post_message(
    session: AsyncSession, user: User, role: str, session_id: str, message: str
) -> tuple[list[ConversationHistory], list[KnowledgeBaseArticle]]:
    """One turn. A requester's message gets a bot answer plus suggestions
    (§12 steps 3–4) — unless an agent has taken the conversation over, after
    which the bot stays out of the way (§12 step 7)."""
    require_access(user, role, session_id)
    history = await transcript(session, session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if any(row.ticket_id for row in history):
        raise HTTPException(status_code=409, detail="This conversation is already a ticket")

    if role in STAFF:
        new = [_say(session, session_id, "agent", message)]
        await session.commit()
        return new, []

    new = [_say(session, session_id, "user", message)]
    if any(row.speaker == "agent" for row in history):
        await session.commit()
        return new, []

    articles = await _suggest(session, role, message)
    new.append(_say(session, session_id, "bot", await _bot_answer(message, articles, history)))
    await session.commit()
    return new, articles


async def active_sessions(session: AsyncSession, limit: int) -> list[dict]:
    """Live, un-converted conversations an agent could join (§12 step 7)."""
    cutoff = datetime.now(UTC) - ACTIVE_WINDOW
    rows = await session.execute(
        sa.select(
            ConversationHistory.session_id,
            sa.func.max(ConversationHistory.created_at).label("last_message_at"),
            sa.func.count().label("message_count"),
            sa.func.bool_or(ConversationHistory.speaker == "agent").label("agent_joined"),
        )
        .where(ConversationHistory.ticket_id.is_(None))
        .group_by(ConversationHistory.session_id)
        .having(sa.func.max(ConversationHistory.created_at) >= cutoff)
        .having(sa.func.bool_or(ConversationHistory.speaker == "user"))  # not just a greeting
        .order_by(sa.desc("last_message_at"))
        .limit(limit)
    )
    return [
        {
            "session_id": sid,
            "last_message_at": last,
            "message_count": count,
            "agent_joined": joined,
            # The owner is in the id (see module docstring), so the console can
            # show who it is without an extra column or an extra query.
            "requester_id": sid.split(":")[0],
        }
        for sid, last, count, joined in rows
    ]


async def end(
    session: AsyncSession, user: User, role: str, session_id: str, resolved: bool
) -> Ticket | None:
    """§12 steps 4–6. Resolved ends the chat as a deflection; unresolved
    converts it into a ticket carrying the whole transcript, then the caller
    runs the same AI pipeline every other channel uses."""
    require_access(user, role, session_id)
    history = await transcript(session, session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if history[0].ticket_id:
        raise HTTPException(status_code=409, detail="This conversation is already a ticket")

    if resolved:
        # ponytail: the deflection log is this bot line; the AI Performance
        # Monitor reads counts off conversation_history rather than a new table.
        _say(session, session_id, "bot", DEFLECTED)
        await session.commit()
        return None

    said = [row.message for row in history if row.speaker == "user"]
    if not said:
        raise HTTPException(status_code=422, detail="Nothing to raise a ticket about yet")
    # The ticket belongs to whoever was chatting, even when an agent who took
    # the conversation over is the one converting it.
    ticket = await tickets.create_ticket(
        session,
        await _owner(session, session_id) or user,
        schemas.TicketCreate(
            subject=said[0][: schemas.SUBJECT_MAX],
            description="\n\n".join(f"{row.speaker}: {row.message}" for row in history)[
                : schemas.BODY_MAX
            ],
            channel="chat",
        ),
    )
    # §12 step 5: the transcript becomes the ticket's history, so the agent
    # never asks the requester to repeat themselves.
    await session.execute(
        sa.update(ConversationHistory)
        .where(ConversationHistory.session_id == session_id)
        .values(ticket_id=ticket.id)
    )
    await session.commit()
    return ticket
