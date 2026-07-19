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
from app.auth.deps import scope_tickets_to_caller
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
from app.sla import timers
from app.tickets import schemas
from app.workflow import engine

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


def _mime_allowed(mime: str) -> bool:
    return mime.startswith("image/") or mime in ALLOWED_MIME_TYPES


# --- Access ---


async def get_ticket_scoped(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> Ticket:
    """404 for both missing and out-of-scope — no existence leak across requesters."""
    criterion = scope_tickets_to_caller(caller, role, Ticket, Queue, User)
    result = await session.execute(sa.select(Ticket).where(Ticket.id == ticket_id, criterion))
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
    await session.commit()
    await session.refresh(ticket)
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
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
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
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    await engine.transition(session, ticket, new_status, caller.id, role)
    await session.commit()
    return ticket


async def reopen_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> Ticket:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    if ticket.merged_into_ticket_id:
        raise HTTPException(status_code=409, detail="Merged tickets cannot be reopened")
    if ticket.closed_at and _now() - ticket.closed_at > timedelta(days=REOPEN_WINDOW_DAYS):
        raise HTTPException(status_code=409, detail="Reopen window has elapsed")
    await engine.transition(session, ticket, "reopened", caller.id, role)
    # §10: Reopened → In Progress is an automatic system re-entry
    await engine.transition(session, ticket, "in_progress", None, None)
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
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    before = {"assignee_id": str(ticket.assignee_id), "queue_id": str(ticket.queue_id)}
    if body.assignee_id:
        assignee = await _get_or_422(session, User, body.assignee_id, "assignee")
        if not assignee.is_active:
            raise HTTPException(status_code=422, detail="Assignee is deactivated")
        ticket.assignee_id = assignee.id
    if body.queue_id:
        await _get_or_422(session, Queue, body.queue_id, "queue")
        ticket.queue_id = body.queue_id
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
    await session.commit()
    return ticket


async def escalate_ticket(
    session: AsyncSession, caller: User, role: str, ticket_id: uuid.UUID
) -> Ticket:
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
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
    secondary = await get_ticket_scoped(session, caller, role, ticket_id)
    primary = await get_ticket_scoped(session, caller, role, target_id)
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


async def _record_mentions(session: AsyncSession, comment: Comment) -> None:
    emails = set(_MENTION_RE.findall(comment.body))
    if not emails:
        return
    result = await session.execute(sa.select(User.id).where(User.email.in_(emails)))
    for user_id in result.scalars():
        session.add(CommentMention(comment_id=comment.id, mentioned_user_id=user_id))


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
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    if body.is_internal and role not in STAFF:
        raise HTTPException(status_code=403, detail="Only staff may write internal notes")
    comment = Comment(
        ticket_id=ticket.id, author_id=caller.id, body=body.body, is_internal=body.is_internal
    )
    session.add(comment)
    await session.flush()
    await _record_mentions(session, comment)
    # §10 side effects of replying. The response timer needs no write to "stop":
    # first-reply time is derived from this comments row against response_due_at.
    if role in STAFF and not body.is_internal and ticket.status == "open":
        await engine.transition(session, ticket, "in_progress", caller.id, role)
    elif role == "requester" and ticket.status == "on_hold":
        # Automatic system resume when the requester replies
        await engine.transition(session, ticket, "in_progress", None, None)
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
    ticket = await get_ticket_scoped(session, caller, role, ticket_id)
    if await session.get(Tag, tag_id) is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    if await session.get(TicketTag, (ticket_id, tag_id)):
        raise HTTPException(status_code=409, detail="Ticket already has this tag")
    session.add(TicketTag(ticket_id=ticket_id, tag_id=tag_id, added_by=caller.id))
    audit.log(session, "ticket", ticket.id, caller.id, "tag_added", after={"tag_id": str(tag_id)})
    await session.commit()
    return ticket
