"""Multi-channel intake endpoints (Phase 13): inbound email + the chat widget.

TRD §3 names no paths for either channel — email arrives at a mail server, not
an API — so these are new: `/intake/email` for a provider webhook, `/chat/...`
for the widget.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.ai import pipeline
from app.auth.deps import CurrentUser, SessionDep, require_role, role_name
from app.config import get_settings
from app.intake import chat_service, email_service
from app.models import User
from app.rate_limit import rate_limit
from app.tickets.schemas import BODY_MAX, TicketOut
from app.validators import SafeText

router = APIRouter(tags=["intake"])

StaffUser = Annotated[User, Depends(require_role("agent", "team_lead", "admin"))]
chat_limiter = rate_limit(60)  # per-user; a chat turn is cheap but not free


# --- Email (App Flow §11) ---


class InboundEmail(BaseModel):
    """The raw RFC-822 message, exactly as the provider received it — parsing
    it here rather than trusting a provider's pre-split JSON keeps one parser
    for both the webhook and the IMAP poller."""

    raw: str = Field(min_length=1, max_length=10_000_000)


@router.post("/intake/email", status_code=202, dependencies=[Depends(rate_limit(120))])
async def inbound_email(
    body: InboundEmail,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    x_inbound_token: Annotated[str | None, Header()] = None,
) -> dict:
    """Unauthenticated by design (mail providers hold no JWT) — a shared secret
    guards it instead, and an unset secret disables the route entirely rather
    than leaving an open door."""
    expected = get_settings().inbound_email_token
    if not expected:
        raise HTTPException(status_code=503, detail="Inbound email is not configured")
    if x_inbound_token != expected:
        raise HTTPException(status_code=401, detail="Invalid inbound token")

    result = await email_service.handle_raw_email(session, body.raw.encode())
    if result.action == "created" and result.ticket_id:
        # Same handoff as portal creation: the pipeline never blocks intake.
        background_tasks.add_task(pipeline.run_for_ticket, result.ticket_id)
    return result.as_dict()


# --- Chat widget (App Flow §12) ---


class ChatMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    speaker: str
    message: str
    created_at: datetime


class ChatArticle(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str


class ChatSession(BaseModel):
    session_id: str
    ticket_id: uuid.UUID | None
    messages: list[ChatMessage]


class ChatTurn(BaseModel):
    messages: list[ChatMessage]
    articles: list[ChatArticle]


class ChatSend(BaseModel):
    message: SafeText = Field(min_length=1, max_length=BODY_MAX)


class ChatEnd(BaseModel):
    resolved: bool


class ChatSessionSummary(BaseModel):
    session_id: str
    requester_id: str
    last_message_at: datetime
    message_count: int
    agent_joined: bool


@router.post("/chat/sessions", status_code=201)
async def start_chat(caller: CurrentUser, session: SessionDep) -> ChatSession:
    session_id, messages = await chat_service.start(session, caller)
    return ChatSession(
        session_id=session_id,
        ticket_id=None,
        messages=[ChatMessage.model_validate(m) for m in messages],
    )


@router.get("/chat/sessions")
async def list_chat_sessions(
    caller: StaffUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[ChatSessionSummary]:
    """Live conversations available for takeover. Staff only — a requester has
    exactly one session and already holds its id."""
    return [ChatSessionSummary(**row) for row in await chat_service.active_sessions(session, limit)]


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(
    session_id: str, caller: CurrentUser, session: SessionDep
) -> ChatSession:
    role = await role_name(session, caller.role_id)
    chat_service.require_access(caller, role, session_id)
    messages = await chat_service.transcript(session, session_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return ChatSession(
        session_id=session_id,
        ticket_id=messages[0].ticket_id,
        messages=[ChatMessage.model_validate(m) for m in messages],
    )


@router.post("/chat/sessions/{session_id}/messages", dependencies=[Depends(chat_limiter)])
async def send_chat_message(
    session_id: str, body: ChatSend, caller: CurrentUser, session: SessionDep
) -> ChatTurn:
    role = await role_name(session, caller.role_id)
    messages, articles = await chat_service.post_message(
        session, caller, role, session_id, body.message
    )
    return ChatTurn(
        messages=[ChatMessage.model_validate(m) for m in messages],
        articles=[ChatArticle.model_validate(a) for a in articles],
    )


@router.post("/chat/sessions/{session_id}/end")
async def end_chat(
    session_id: str,
    body: ChatEnd,
    caller: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TicketOut | None:
    """Resolved → deflection, no ticket (null body). Unresolved → the transcript
    becomes a ticket and runs the standard pipeline."""
    role = await role_name(session, caller.role_id)
    ticket = await chat_service.end(session, caller, role, session_id, body.resolved)
    if ticket is None:
        return None
    background_tasks.add_task(pipeline.run_for_ticket, ticket.id)
    return TicketOut.model_validate(ticket)
