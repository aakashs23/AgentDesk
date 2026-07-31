"""Ticket domain business logic (Implementation Plan Phase 4).

Row-level access follows Document 05 §6 via `scope_tickets_to_caller`; every
status change routes through the workflow engine; every mutation is audited.
"""

import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import sqlalchemy as sa
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.auth.deps import role_name, scope_tickets_to_caller
from app.config import get_settings
from app.models import (
    Attachment,
    Category,
    Comment,
    CommentMention,
    Priority,
    Queue,
    Role,
    Tag,
    Ticket,
    TicketStatusHistory,
    TicketTag,
    User,
)
from app.notifications import service as notifications
from app.sla import timers
from app.tickets import schemas
from app.webhooks import service as webhooks
from app.workflow import automation, engine

CHANNELS = {"portal", "email", "chat"}
STAFF = {"agent", "team_lead", "admin"}

# TRD Section 8: images, PDFs, common office docs
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# ponytail: constant until the Admin Configuration Service (Phase 9) makes it a setting
REOPEN_WINDOW_DAYS = 7

_MENTION_RE = re.compile(r"@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def _now() -> datetime:
    return datetime.now(UTC)


# The declared content type is whatever the client wrote in the part header, so
# it is checked against the bytes. Types with no recognisable signature (SVG and
# other text-based images) have no entry and fall through.
_MAGIC_PREFIXES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/bmp": (b"BM",),
    "image/webp": (b"RIFF",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
    "application/pdf": (b"%PDF",),
    # every OOXML document is a zip container
    **{mime: (b"PK\x03\x04",) for mime in ALLOWED_MIME_TYPES if mime != "application/pdf"},
}


def _mime_allowed(mime: str) -> bool:
    return mime.startswith("image/") or mime in ALLOWED_MIME_TYPES


def _content_matches(mime: str, content: bytes) -> bool:
    prefixes = _MAGIC_PREFIXES.get(mime)
    return prefixes is None or content.startswith(prefixes)


# --- Access ---


async def get_ticket_scoped(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID, for_update: bool = False
) -> Ticket:
    """404 for both missing and out-of-scope — no existence leak across requesters.

    `for_update` takes a row lock, and every path that reads the ticket, decides
    from what it read, then writes must use it: without it concurrent requests
    all validate against the same stale row (duplicate status-history rows, lost
    `reopened_count` increments). The scoping criterion is a subquery, never an
    outer join, so FOR UPDATE applies cleanly to `tickets`.
    """
    criterion = scope_tickets_to_caller(caller, role, Ticket, Queue, User)
    query = sa.select(Ticket).where(Ticket.id == ticket_id, criterion)
    if for_update:
        query = query.with_for_update()
    result = await session.execute(query)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


async def _get_or_422(session: AsyncSession, model, entity_id: uuid.UUID, label: str):
    row = await session.get(model, entity_id)
    if row is None:
        raise HTTPException(status_code=422, detail=f"Unknown {label}")
    return row


# --- Tickets ---


async def create_ticket(session: AsyncSession, caller: User, body: schemas.TicketCreate) -> Ticket:
    if body.channel not in CHANNELS:
        raise HTTPException(status_code=422, detail=f"Unknown channel: {body.channel}")
    if body.category_id:
        await _get_or_422(session, Category, body.category_id, "category")
    ticket = Ticket(
        subject=body.subject,
        description=body.description,
        requester_id=caller.id,
        category_id=body.category_id,
        channel=body.channel,
    )
    session.add(ticket)
    await session.flush()  # assigns display_id
    # Phase 4: no AI classification yet, so no priority → timers usually stay null
    # until manual classification; anchored at created_at either way (App Flow §16).
    await timers.start_timers(session, ticket, ticket.created_at)
    engine.record_created(session, ticket, caller.id)
    await automation.dispatch(session, "ticket_created", ticket)
    await session.commit()
    await session.refresh(ticket)
    webhooks.dispatch("ticket_created", webhooks.ticket_payload("ticket_created", ticket))
    return ticket


async def list_tickets(
    session: AsyncSession,
    caller: User,
    role: str,
    status: str | None,
    limit: int,
    offset: int,
) -> list[Ticket]:
    criterion = scope_tickets_to_caller(caller, role, Ticket, Queue, User)
    query = sa.select(Ticket).where(criterion)
    if status:
        query = query.where(Ticket.status == status)
    query = query.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    return list((await session.execute(query)).scalars())


async def update_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID, body: schemas.TicketUpdate
) -> Ticket:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    changes = body.model_dump(exclude_unset=True)
    if role not in STAFF and not set(changes) <= {"subject", "description"}:
        raise HTTPException(status_code=403, detail="Only staff may classify tickets")
    for field, model, label in (
        ("category_id", Category, "category"),
        ("priority_id", Priority, "priority"),
        ("queue_id", Queue, "queue"),
    ):
        if changes.get(field):
            await _get_or_422(session, model, changes[field], label)
    before = {k: str(getattr(ticket, k)) for k in changes}
    for key, value in changes.items():
        setattr(ticket, key, value)
    ticket.updated_at = _now()
    # First classification starts the SLA clocks, anchored at creation (§16)
    await timers.start_timers(session, ticket, ticket.created_at)
    audit.log(
        session,
        "ticket",
        ticket.id,
        caller.id,
        "updated",
        before=before,
        after={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return ticket


async def change_status(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID, new_status: str
) -> Ticket:
    if new_status == "reopened":
        return await reopen_ticket(session, caller, role, ticket_id)
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    await engine.transition(session, ticket, new_status, caller.id, role)
    await automation.dispatch(session, "status_changed", ticket)
    # §17: keep the requester informed of their ticket's progress (closure is its
    # own trigger so preferences/templates can treat it separately).
    if ticket.requester_id != caller.id:
        trigger = "ticket_closed" if new_status == "closed" else "status_changed"
        ref = f"AGT-{ticket.display_id}"
        await notifications.notify(
            session,
            ticket.requester_id,
            ticket.id,
            trigger,
            f"[{ref}] {'Closed' if new_status == 'closed' else 'Status: ' + new_status}",
            f"Ticket {ref} — {ticket.subject} — is now {new_status}.",
        )
    await session.commit()
    webhooks.dispatch("status_changed", webhooks.ticket_payload("status_changed", ticket))
    return ticket


async def reopen_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> Ticket:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    if ticket.merged_into_ticket_id:
        raise HTTPException(status_code=409, detail="Merged tickets cannot be reopened")
    if ticket.closed_at and _now() - ticket.closed_at > timedelta(days=REOPEN_WINDOW_DAYS):
        raise HTTPException(status_code=409, detail="Reopen window has elapsed")
    await engine.transition(session, ticket, "reopened", caller.id, role)
    # §10: Reopened → In Progress is an automatic system re-entry
    await engine.transition(session, ticket, "in_progress", None, None)
    await automation.dispatch(session, "status_changed", ticket)
    await session.commit()
    return ticket


async def status_history(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> list[TicketStatusHistory]:
    await get_ticket_scoped(session, caller, role, ticket_id)  # team-scoped for leads
    result = await session.execute(
        sa.select(TicketStatusHistory)
        .where(TicketStatusHistory.ticket_id == ticket_id)
        .order_by(TicketStatusHistory.changed_at)
    )
    return list(result.scalars())


# --- Assignment / escalation ---


async def assign_ticket(
    session: AsyncSession,
    caller: User,
    role: str,
    ticket_id: uuid.UUID,
    body: schemas.AssignRequest,
) -> Ticket:
    if body.assignee_id is None and body.queue_id is None:
        raise HTTPException(status_code=422, detail="Provide assignee_id and/or queue_id")
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    before = {"assignee_id": str(ticket.assignee_id), "queue_id": str(ticket.queue_id)}
    if body.queue_id:
        await _get_or_422(session, Queue, body.queue_id, "queue")
        ticket.queue_id = body.queue_id
    if body.assignee_id:
        assignee = await _get_or_422(session, User, body.assignee_id, "assignee")
        if not assignee.is_active:
            raise HTTPException(status_code=422, detail="Assignee is deactivated")
        # A requester assignee cannot see the ticket at all (they are scoped by
        # requester_id), so it would look assigned while sitting in nobody's queue
        if await role_name(session, assignee.role_id) not in STAFF:
            raise HTTPException(status_code=422, detail="Assignee cannot work tickets")
        # The queue model exists to keep work inside a team; crossing it silently
        # defeats it (§6 visibility still holds either way, so this is routing).
        if ticket.queue_id:
            queue = await session.get(Queue, ticket.queue_id)
            if queue.team_id and assignee.team_id != queue.team_id:
                raise HTTPException(status_code=422, detail="Assignee is not on the queue's team")
        ticket.assignee_id = assignee.id
    ticket.updated_at = _now()
    audit.log(
        session,
        "ticket",
        ticket.id,
        caller.id,
        "assigned",
        before=before,
        after={"assignee_id": str(ticket.assignee_id), "queue_id": str(ticket.queue_id)},
    )
    if ticket.status == "new":  # manual pickup moves New → Open (§10)
        await engine.transition(session, ticket, "open", caller.id, role)
    if body.assignee_id and body.assignee_id != caller.id:  # §17 assignment trigger
        ref = f"AGT-{ticket.display_id}"
        await notifications.notify(
            session,
            body.assignee_id,
            ticket.id,
            "ticket_assigned",
            f"[{ref}] Assigned to you",
            f"Ticket {ref} — {ticket.subject} — was assigned to you.",
        )
    await session.commit()
    return ticket


async def escalate_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> Ticket:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    team_id = None
    if ticket.queue_id:
        team_id = (await session.get(Queue, ticket.queue_id)).team_id
    team_id = team_id or caller.team_id
    result = await session.execute(
        sa.select(User)
        .join(Role, Role.id == User.role_id)
        .where(Role.name == "team_lead", User.team_id == team_id, User.is_active.is_(True))
        .limit(1)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=409, detail="No team lead available to escalate to")
    before = {"assignee_id": str(ticket.assignee_id)}
    ticket.assignee_id = lead.id
    ticket.updated_at = _now()
    audit.log(
        session,
        "ticket",
        ticket.id,
        caller.id,
        "escalated",
        before=before,
        after={"assignee_id": str(lead.id)},
    )
    ref = f"AGT-{ticket.display_id}"
    await notifications.notify(
        session,
        lead.id,
        ticket.id,
        "escalation",
        f"[{ref}] Escalated to you",
        f"Ticket {ref} — {ticket.subject} — was escalated to you.",
    )
    await session.commit()
    return ticket


# --- Merge / split ---


def _system_comment(session: AsyncSession, ticket_id: uuid.UUID, body: str) -> None:
    session.add(Comment(ticket_id=ticket_id, author_id=None, body=body))


async def merge_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID, target_id: uuid.UUID
) -> Ticket:
    if ticket_id == target_id:
        raise HTTPException(status_code=422, detail="Cannot merge a ticket into itself")
    # Both rows are read-then-written, so both are locked — always lowest id
    # first, or two reciprocal merges deadlock holding the row the other needs.
    locked = {
        tid: await get_ticket_scoped(session, caller, role, tid, for_update=True)
        for tid in sorted((ticket_id, target_id))
    }
    secondary, primary = locked[ticket_id], locked[target_id]
    if secondary.merged_into_ticket_id or secondary.status == "closed":
        raise HTTPException(status_code=409, detail="Ticket is already closed or merged")
    if primary.merged_into_ticket_id or primary.status == "closed":
        raise HTTPException(status_code=409, detail="Target ticket is closed or merged")
    secondary.merged_into_ticket_id = primary.id
    engine.record_merged(session, secondary, caller.id)
    # §20: the merge lands in the audit log with both ticket IDs
    audit.log(
        session,
        "ticket",
        primary.id,
        caller.id,
        "merge_received",
        after={"merged_ticket_id": str(secondary.id)},
    )
    _system_comment(
        session,
        primary.id,
        f"Ticket AGT-{secondary.display_id} was merged into this ticket.",
    )
    await session.commit()
    return primary


async def split_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID, body: schemas.SplitRequest
) -> list[Ticket]:
    parent = await get_ticket_scoped(session, caller, role, ticket_id)
    children: list[Ticket] = []
    for part in body.subtickets:
        child = Ticket(
            subject=part.subject,
            description=part.description,
            requester_id=parent.requester_id,
            category_id=parent.category_id,
            priority_id=parent.priority_id,
            queue_id=parent.queue_id,
            channel=parent.channel,
        )
        session.add(child)
        await session.flush()
        await timers.start_timers(session, child, child.created_at)
        engine.record_created(session, child, caller.id)
        children.append(child)
    audit.log(
        session,
        "ticket",
        parent.id,
        caller.id,
        "split",
        after={"child_ticket_ids": [str(c.id) for c in children]},
    )
    _system_comment(
        session,
        parent.id,
        "Split into: " + ", ".join(f"AGT-{c.display_id}" for c in children),
    )
    await session.commit()
    for child in children:
        await session.refresh(child)
    return children


# --- Comments ---


async def _record_mentions(session: AsyncSession, comment: Comment, ticket: Ticket) -> None:
    emails = set(_MENTION_RE.findall(comment.body))
    if not emails:
        return
    result = await session.execute(sa.select(User.id).where(User.email.in_(emails)))
    ref = f"AGT-{ticket.display_id}"
    for user_id in result.scalars():
        session.add(CommentMention(comment_id=comment.id, mentioned_user_id=user_id))
        if user_id != comment.author_id:  # §17 @mention trigger
            await notifications.notify(
                session,
                user_id,
                ticket.id,
                "mention",
                f"[{ref}] You were mentioned",
                f"You were mentioned on ticket {ref} — {ticket.subject}.",
            )


async def list_comments(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> list[Comment]:
    await get_ticket_scoped(session, caller, role, ticket_id)
    query = sa.select(Comment).where(Comment.ticket_id == ticket_id)
    if role == "requester":  # internal notes are staff-only (Doc 05 §6)
        query = query.where(Comment.is_internal.is_(False))
    return list((await session.execute(query.order_by(Comment.created_at))).scalars())


async def create_comment(
    session: AsyncSession,
    caller: User,
    role: str,
    ticket_id: uuid.UUID,
    body: schemas.CommentCreate,
) -> Comment:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    if body.is_internal and role not in STAFF:
        raise HTTPException(status_code=403, detail="Only staff may write internal notes")
    comment = Comment(
        ticket_id=ticket.id, author_id=caller.id, body=body.body, is_internal=body.is_internal
    )
    session.add(comment)
    await session.flush()
    await _record_mentions(session, comment, ticket)
    # §10 side effects of replying. The response timer needs no write to "stop":
    # first-reply time is derived from this comments row against response_due_at.
    if role in STAFF and not body.is_internal and ticket.status == "open":
        await engine.transition(session, ticket, "in_progress", caller.id, role)
    elif role == "requester" and ticket.status == "on_hold":
        # Automatic system resume when the requester replies
        await engine.transition(session, ticket, "in_progress", None, None)
    await automation.dispatch(session, "comment_added", ticket)
    # §17 reply trigger — a public reply notifies the other side of the thread.
    if not body.is_internal:
        recipient = ticket.assignee_id if role == "requester" else ticket.requester_id
        if recipient and recipient != caller.id:
            ref = f"AGT-{ticket.display_id}"
            await notifications.notify(
                session,
                recipient,
                ticket.id,
                "ticket_replied",
                f"[{ref}] New reply",
                f"There is a new reply on ticket {ref} — {ticket.subject}.",
            )
    await session.commit()
    return comment


async def _get_comment_as_author_or_admin(
    session: AsyncSession, caller: User, role: str, comment_id: uuid.UUID
) -> Comment:
    comment = await session.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if role != "admin" and comment.author_id != caller.id:
        raise HTTPException(status_code=403, detail="Not the comment author")
    return comment


async def update_comment(
    session: AsyncSession, caller: User, role: str, comment_id: uuid.UUID, body: str
) -> Comment:
    comment = await _get_comment_as_author_or_admin(session, caller, role, comment_id)
    comment.body = body
    comment.updated_at = _now()  # set only if edited (Document 05)
    await session.commit()
    return comment


async def delete_comment(
    session: AsyncSession, caller: User, role: str, comment_id: uuid.UUID
) -> None:
    """Hard delete, by decision — Doc 05 (`comments`) has no `deleted_at`.

    That makes the audit row below the only surviving copy, so `before` must
    keep carrying the body: drop it and the delete becomes unrecoverable.
    """
    comment = await _get_comment_as_author_or_admin(session, caller, role, comment_id)
    await session.execute(sa.delete(CommentMention).where(CommentMention.comment_id == comment.id))
    await session.execute(
        sa.update(Attachment).where(Attachment.comment_id == comment.id).values(comment_id=None)
    )
    audit.log(
        session,
        "comment",
        comment.id,
        caller.id,
        "deleted",
        before={"ticket_id": str(comment.ticket_id), "body": comment.body},
    )
    await session.delete(comment)
    await session.commit()


# --- Attachments ---


async def add_attachment(
    session: AsyncSession,
    caller: User,
    role: str,
    ticket_id: uuid.UUID,
    file: UploadFile,
    comment_id: uuid.UUID | None,
    replaces_attachment_id: uuid.UUID | None,
) -> Attachment:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    mime = file.content_type or "application/octet-stream"
    if not _mime_allowed(mime):
        raise HTTPException(status_code=415, detail=f"File type not allowed: {mime}")
    content = await file.read()  # ponytail: whole file in memory — fine under a 10MB cap
    settings = get_settings()
    if len(content) > settings.attachment_max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.attachment_max_bytes // (1024 * 1024)}MB limit",
        )
    if not content:
        raise HTTPException(status_code=422, detail="File is empty")
    if not _content_matches(mime, content):
        raise HTTPException(status_code=415, detail=f"File contents are not {mime}")

    replaced = None
    if replaces_attachment_id:
        replaced = await session.get(Attachment, replaces_attachment_id)
        if replaced is None or replaced.ticket_id != ticket.id or replaced.deleted_at:
            raise HTTPException(status_code=422, detail="Unknown attachment to replace")

    file_name = os.path.basename(file.filename or "upload")
    attachment = Attachment(
        ticket_id=ticket.id,
        comment_id=comment_id,
        uploader_id=caller.id,
        file_name=file_name,
        storage_path="",  # set below, needs the generated id
        mime_type=mime,
        size_bytes=len(content),
        version=replaced.version + 1 if replaced else 1,
    )
    # Path convention from Document 05 §9: /attachments/{ticket_id}/{attachment_id}_{filename}
    path = Path(settings.attachment_dir) / str(ticket.id) / f"{attachment.id}_{file_name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    attachment.storage_path = str(path)
    session.add(attachment)
    if replaced:
        await session.flush()  # new row must exist before the old row's FK points at it
        replaced.replaced_by_attachment_id = attachment.id
    audit.log(
        session,
        "attachment",
        attachment.id,
        caller.id,
        "uploaded",
        after={"ticket_id": str(ticket.id), "file_name": file_name, "version": attachment.version},
    )
    await session.commit()
    return attachment


async def list_attachments(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> list[Attachment]:
    """A ticket's live attachments, for the Attachments tab (App Flow §2).

    Soft-deleted and superseded versions are excluded: the tab shows what is
    currently attached, not the upload history (`version` /
    `replaced_by_attachment_id` keep that).
    """
    await get_ticket_scoped(session, caller, role, ticket_id)
    query = (
        sa.select(Attachment)
        .where(
            Attachment.ticket_id == ticket_id,
            Attachment.deleted_at.is_(None),
            Attachment.replaced_by_attachment_id.is_(None),
        )
        .order_by(Attachment.created_at)
    )
    return list((await session.execute(query)).scalars())


async def get_attachment_file(
    session: AsyncSession, caller: User, role: str, attachment_id: uuid.UUID
) -> Attachment:
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None or attachment.deleted_at:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await get_ticket_scoped(session, caller, role, attachment.ticket_id)
    if not os.path.isfile(attachment.storage_path):  # noqa: ASYNC240 — one local stat call
        raise HTTPException(status_code=404, detail="Attachment not found")
    return attachment


async def delete_attachment(
    session: AsyncSession, caller: User, role: str, attachment_id: uuid.UUID
) -> None:
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None or attachment.deleted_at:
        raise HTTPException(status_code=404, detail="Attachment not found")
    await get_ticket_scoped(session, caller, role, attachment.ticket_id)
    attachment.deleted_at = _now()  # soft delete keeps the audit trail intact (Doc 05)
    audit.log(
        session,
        "attachment",
        attachment.id,
        caller.id,
        "deleted",
        before={"ticket_id": str(attachment.ticket_id), "file_name": attachment.file_name},
    )
    await session.commit()


# --- Tags ---


async def list_tags(session: AsyncSession) -> list[Tag]:
    return list((await session.execute(sa.select(Tag).order_by(Tag.name))).scalars())


async def create_tag(session: AsyncSession, name: str) -> Tag:
    existing = (await session.execute(sa.select(Tag).where(Tag.name == name))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = Tag(name=name)
    session.add(tag)
    await session.commit()
    return tag


async def attach_tag(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID, tag_id: uuid.UUID
) -> Ticket:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id, for_update=True)
    if await session.get(Tag, tag_id) is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    if await session.get(TicketTag, (ticket_id, tag_id)):
        raise HTTPException(status_code=409, detail="Ticket already has this tag")
    session.add(TicketTag(ticket_id=ticket_id, tag_id=tag_id, added_by=caller.id))
    audit.log(session, "ticket", ticket.id, caller.id, "tag_added", after={"tag_id": str(tag_id)})
    await automation.dispatch(session, "tag_added", ticket)
    await session.commit()
    return ticket
