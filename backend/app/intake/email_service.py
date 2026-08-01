"""Email-to-ticket intake (Implementation Plan Phase 13; App Flow §11).

One entry point, `handle_raw_email`, serving both ways a message can arrive —
the IMAP poller and `POST /intake/email`. It follows §11 in order: parse,
malformed → manual review, match the thread, otherwise create a ticket through
the *same* `tickets.service.create_ticket` the portal form uses, so channel
differences never fork the domain logic.

Two schema-forced decisions, both deliberate:

- **The manual review queue is a `queues` row.** Doc 05 defines no review table
  and the schema invariant forbids adding one; a queue is what "a place work
  waits for a human" already means everywhere else in this system, and it
  inherits queue scoping, the agent console and reporting for free.
- **`tickets.requester_id` is NOT NULL**, so an email from an address with no
  account auto-provisions a requester (unusable password — the mailbox owner
  claims it via password reset), and a malformed message with no readable
  sender at all is filed against a single placeholder account.
"""

import asyncio
import imaplib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers, UploadFile

from app.auth import security
from app.config import get_settings
from app.intake import parser
from app.intake.parser import ParsedEmail
from app.models import Comment, Queue, Role, Ticket, User
from app.notifications import mailer
from app.tickets import schemas
from app.tickets import service as tickets

logger = logging.getLogger("agentdesk.intake")

MANUAL_REVIEW_QUEUE = "Manual Review"
UNKNOWN_SENDER_EMAIL = "unknown-sender@agentdesk.invalid"
# §11 step 6's "sender + recent-activity" fallback, used only when neither the
# subject tag nor the thread headers matched.
RECENT_THREAD_WINDOW = timedelta(days=7)
CLOSED_STATUSES = ("closed", "resolved")


class IntakeResult:
    """What happened to one message, for the caller's log/response and so the
    router knows whether the AI pipeline still has to run."""

    def __init__(self, action: str, ticket_id: uuid.UUID | None = None, detail: str = ""):
        self.action = action  # created / appended / manual_review / duplicate
        self.ticket_id = ticket_id
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "ticket_id": str(self.ticket_id) if self.ticket_id else None,
            "detail": self.detail,
        }


async def _user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        sa.select(User).where(sa.func.lower(User.email) == email.strip().lower())
    )
    return result.scalar_one_or_none()


async def _requester_for(session: AsyncSession, email: str, full_name: str) -> User:
    """The sender's account, provisioned on first contact. A deactivated account
    stays deactivated — it just cannot be logged into, its mail still files."""
    existing = await _user_by_email(session, email)
    if existing:
        return existing
    role_id = (
        await session.execute(sa.select(Role.id).where(Role.name == "requester"))
    ).scalar_one()
    user = User(
        email=email,
        # Unusable by construction; the raw value is never known to anyone.
        password_hash=security.hash_password(security.new_raw_token()),
        full_name=full_name or email,
        role_id=role_id,
    )
    session.add(user)
    await session.flush()
    logger.info("provisioned requester %s from inbound email", email)
    return user


async def _manual_review_queue(session: AsyncSession) -> Queue:
    queue = (
        await session.execute(sa.select(Queue).where(Queue.name == MANUAL_REVIEW_QUEUE))
    ).scalar_one_or_none()
    if queue is None:
        queue = Queue(name=MANUAL_REVIEW_QUEUE)
        session.add(queue)
        await session.flush()
    return queue


async def _attach(session: AsyncSession, ticket: Ticket, requester: User, parsed: ParsedEmail):
    """Reuses the portal upload path so email attachments get the same MIME
    allowlist, magic-byte check and size cap (§11 step 5 says exactly that).
    A rejected file must not cost the ticket, so each failure is logged only."""
    for file_name, mime, content in parsed.attachments:
        upload = UploadFile(
            file=BytesIO(content),
            size=len(content),
            filename=file_name,
            headers=Headers({"content-type": mime}),
        )
        try:
            await tickets.add_attachment(
                session, requester, "requester", ticket.id, upload, None, None
            )
        except HTTPException as exc:
            logger.warning(
                "email attachment %r rejected for ticket %s: %s", file_name, ticket.id, exc.detail
            )


async def _find_by_thread(session: AsyncSession, parsed: ParsedEmail) -> Ticket | None:
    """§11 step 6, in precedence order: subject tag, thread headers, then
    sender + same normalised subject on a still-open recent ticket."""
    display_id = parser.display_id_in(parsed.subject)
    if display_id is not None:
        ticket = (
            await session.execute(sa.select(Ticket).where(Ticket.display_id == display_id))
        ).scalar_one_or_none()
        if ticket is not None:
            return ticket
    if parsed.references:
        ticket = (
            (
                await session.execute(
                    sa.select(Ticket)
                    .where(Ticket.source_email_message_id.in_(parsed.references))
                    .order_by(Ticket.created_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if ticket is not None:
            return ticket

    requester = await _user_by_email(session, parsed.sender_email)
    if requester is None:
        return None
    cutoff = datetime.now(UTC) - RECENT_THREAD_WINDOW
    candidates = (
        await session.execute(
            sa.select(Ticket)
            .where(
                Ticket.requester_id == requester.id,
                Ticket.status.not_in(CLOSED_STATUSES),
                Ticket.updated_at >= cutoff,
            )
            .order_by(Ticket.updated_at.desc())
            .limit(20)
        )
    ).scalars()
    target = parser.normalise_subject(parsed.subject)
    if not target:
        return None
    return next((t for t in candidates if parser.normalise_subject(t.subject) == target), None)


async def _already_seen(session: AsyncSession, parsed: ParsedEmail) -> bool:
    """Webhook retries and a re-polled mailbox must not double-file."""
    if parsed.message_id:
        seen = (
            await session.execute(
                sa.select(Ticket.id).where(Ticket.source_email_message_id == parsed.message_id)
            )
        ).first()
        if seen:
            return True
    return False


async def _append_reply(session: AsyncSession, ticket: Ticket, parsed: ParsedEmail) -> IntakeResult:
    requester = await _requester_for(session, parsed.sender_email, parsed.sender_name)
    duplicate = (
        await session.execute(
            sa.select(Comment.id).where(
                Comment.ticket_id == ticket.id,
                Comment.author_id == requester.id,
                Comment.body == parsed.body,
            )
        )
    ).first()
    if duplicate:
        return IntakeResult("duplicate", ticket.id, "reply already recorded")
    # Through the domain service, so the reply gets §10's on_hold resume, the
    # reply notification to the assignee and the automation dispatch.
    await tickets.create_comment(
        session,
        requester,
        "requester",
        ticket.id,
        schemas.CommentCreate(body=parsed.body[: schemas.BODY_MAX]),
    )
    await _attach(session, ticket, requester, parsed)
    return IntakeResult("appended", ticket.id, f"reply appended to AGT-{ticket.display_id}")


async def _file_for_manual_review(
    session: AsyncSession, raw: bytes, parsed: ParsedEmail
) -> IntakeResult:
    sender = parsed.sender_email if "@" in parsed.sender_email else UNKNOWN_SENDER_EMAIL
    requester = await _requester_for(session, sender, parsed.sender_name or "Unknown sender")
    queue = await _manual_review_queue(session)
    body = parsed.body or raw.decode("utf-8", "replace")
    ticket = Ticket(
        subject=(parsed.subject or "Unparseable email")[: schemas.SUBJECT_MAX],
        description=f"[Manual review: {parsed.problem}]\n\n{body}"[: schemas.BODY_MAX].replace(
            "\x00", ""
        ),
        requester_id=requester.id,
        queue_id=queue.id,
        channel="email",
        source_email_message_id=parsed.message_id,
    )
    session.add(ticket)
    await session.flush()
    # No AI pipeline and no auto-assignment: a human decides what this is first.
    await session.commit()
    logger.warning("email routed to manual review (%s): %s", parsed.problem, parsed.subject)
    return IntakeResult("manual_review", ticket.id, parsed.problem or "malformed")


def send_acknowledgment(to: str, ticket_ref: str, subject: str) -> None:
    """§11 step 8. Deliberately not a `notify(...)` trigger: the ack is what
    carries the ticket ref that makes replies matchable, so it is not something
    a notification preference may switch off."""
    mailer.send_email(
        to,
        f"[{ticket_ref}] {subject}",
        f"Thanks — we've logged your request as {ticket_ref}.\n\n"
        f"Subject: {subject}\n\n"
        "Reply to this email to add to the ticket, or track it in the AgentDesk "
        f"portal at {get_settings().frontend_origin}/portal/tickets.\n",
    )


async def handle_raw_email(session: AsyncSession, raw: bytes) -> IntakeResult:
    """Parse one message and file it. Never raises for bad input — a message we
    cannot understand becomes a manual-review ticket, which is the whole point
    of §11 step 4."""
    parsed = parser.parse(raw)
    if await _already_seen(session, parsed):
        return IntakeResult("duplicate", None, "message-id already ingested")
    if parsed.problem:
        return await _file_for_manual_review(session, raw, parsed)

    existing = await _find_by_thread(session, parsed)
    if existing is not None:
        return await _append_reply(session, existing, parsed)

    requester = await _requester_for(session, parsed.sender_email, parsed.sender_name)
    await session.commit()  # the new account must outlive a later rollback
    ticket = await tickets.create_ticket(
        session,
        requester,
        schemas.TicketCreate(
            subject=(parsed.subject or parsed.body[:80])[: schemas.SUBJECT_MAX],
            description=parsed.body[: schemas.BODY_MAX],
            channel="email",
        ),
    )
    ticket.source_email_message_id = parsed.message_id
    await session.commit()
    await _attach(session, ticket, requester, parsed)
    send_acknowledgment(parsed.sender_email, f"AGT-{ticket.display_id}", ticket.subject)
    return IntakeResult("created", ticket.id, f"created AGT-{ticket.display_id}")


# --- IMAP polling (TRD §3's "IMAP/SMTP"; the webhook route is in router.py) ---


def _fetch_unseen() -> list[bytes]:
    """Blocking; called via `asyncio.to_thread`. Marks each message seen as it
    is read, so a crash mid-batch re-delivers at most the unread remainder —
    and `_already_seen` catches the duplicate if it re-delivers all of it."""
    settings = get_settings()
    messages: list[bytes] = []
    with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as imap:
        imap.login(settings.imap_user, settings.imap_password)
        imap.select("INBOX")
        _typ, data = imap.search(None, "UNSEEN")
        for num in data[0].split():
            _typ, payload = imap.fetch(num, "(RFC822)")
            if payload and isinstance(payload[0], tuple):
                messages.append(payload[0][1])
                imap.store(num, "+FLAGS", "\\Seen")
    return messages


async def poll_forever(interval_seconds: int) -> None:
    """Mailbox poll loop, started from the app lifespan alongside the SLA
    monitor. `imap_host` unset or `imap_poll_seconds` 0 means it never runs."""
    from app.ai import pipeline
    from app.db import _session_factory

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            for raw in await asyncio.to_thread(_fetch_unseen):
                async with _session_factory() as session:
                    result = await handle_raw_email(session, raw)
                logger.info("inbound email: %s (%s)", result.action, result.detail)
                if result.action == "created" and result.ticket_id:
                    await pipeline.run_for_ticket(result.ticket_id)
        except Exception:
            logger.exception("inbound email poll failed")
