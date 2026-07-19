"""Ticket domain endpoints (TRD Section 3: Tickets / Comments / Attachments /
Assignment / Status Updates / Tags). Thin handlers — logic lives in service.py."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.ai import pipeline
from app.auth.deps import CurrentUser, SessionDep, require_role, role_name
from app.models import User
from app.rate_limit import rate_limit
from app.tickets import schemas, service

router = APIRouter(tags=["tickets"])

StaffUser = Annotated[User, Depends(require_role("agent", "team_lead", "admin"))]
create_limiter = rate_limit(20)  # per-user, TRD Section 10 (ticket-creation route)


async def _role(session, user: User) -> str:
    return await role_name(session, user.role_id)


# --- Tickets ---


@router.post("/tickets", status_code=201, dependencies=[Depends(create_limiter)])
async def create_ticket(
    body: schemas.TicketCreate,
    caller: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> schemas.TicketOut:
    ticket = await service.create_ticket(session, caller, body)
    # AI pipeline runs after the response (TRD §11) — creation is never blocked on it
    background_tasks.add_task(pipeline.run_for_ticket, ticket.id)
    return schemas.TicketOut.model_validate(ticket)


@router.get("/tickets")
async def list_tickets(
    caller: CurrentUser,
    session: SessionDep,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[schemas.TicketOut]:
    role = await _role(session, caller)
    tickets = await service.list_tickets(session, caller, role, status, limit, offset)
    return [schemas.TicketOut.model_validate(t) for t in tickets]


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.get_ticket_scoped(session, caller, role, ticket_id)
    )


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: uuid.UUID, body: schemas.TicketUpdate, caller: CurrentUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.update_ticket(session, caller, role, ticket_id, body)
    )


# --- Status ---


@router.patch("/tickets/{ticket_id}/status")
async def change_status(
    ticket_id: uuid.UUID, body: schemas.StatusChange, caller: CurrentUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.change_status(session, caller, role, ticket_id, body.status)
    )


@router.get("/tickets/{ticket_id}/status-history")
async def get_status_history(
    ticket_id: uuid.UUID,
    caller: Annotated[User, Depends(require_role("team_lead", "admin"))],
    session: SessionDep,
) -> list[schemas.StatusHistoryOut]:
    role = await _role(session, caller)
    rows = await service.status_history(session, caller, role, ticket_id)
    return [schemas.StatusHistoryOut.model_validate(r) for r in rows]


@router.post("/tickets/{ticket_id}/reopen")
async def reopen_ticket(
    ticket_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.reopen_ticket(session, caller, role, ticket_id)
    )


# --- Assignment / escalation / merge / split (Agent+) ---


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: uuid.UUID, body: schemas.AssignRequest, caller: StaffUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.assign_ticket(session, caller, role, ticket_id, body)
    )


@router.post("/tickets/{ticket_id}/escalate")
async def escalate_ticket(
    ticket_id: uuid.UUID, caller: StaffUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.escalate_ticket(session, caller, role, ticket_id)
    )


@router.post("/tickets/{ticket_id}/merge")
async def merge_ticket(
    ticket_id: uuid.UUID, body: schemas.MergeRequest, caller: StaffUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.merge_ticket(session, caller, role, ticket_id, body.target_ticket_id)
    )


@router.post("/tickets/{ticket_id}/split", status_code=201)
async def split_ticket(
    ticket_id: uuid.UUID, body: schemas.SplitRequest, caller: StaffUser, session: SessionDep
) -> list[schemas.TicketOut]:
    role = await _role(session, caller)
    children = await service.split_ticket(session, caller, role, ticket_id, body)
    return [schemas.TicketOut.model_validate(c) for c in children]


# --- Comments ---


@router.get("/tickets/{ticket_id}/comments")
async def list_comments(
    ticket_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> list[schemas.CommentOut]:
    role = await _role(session, caller)
    comments = await service.list_comments(session, caller, role, ticket_id)
    return [schemas.CommentOut.model_validate(c) for c in comments]


@router.post("/tickets/{ticket_id}/comments", status_code=201)
async def create_comment(
    ticket_id: uuid.UUID, body: schemas.CommentCreate, caller: CurrentUser, session: SessionDep
) -> schemas.CommentOut:
    role = await _role(session, caller)
    return schemas.CommentOut.model_validate(
        await service.create_comment(session, caller, role, ticket_id, body)
    )


@router.patch("/comments/{comment_id}")
async def update_comment(
    comment_id: uuid.UUID, body: schemas.CommentUpdate, caller: CurrentUser, session: SessionDep
) -> schemas.CommentOut:
    role = await _role(session, caller)
    return schemas.CommentOut.model_validate(
        await service.update_comment(session, caller, role, comment_id, body.body)
    )


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> Response:
    role = await _role(session, caller)
    await service.delete_comment(session, caller, role, comment_id)
    return Response(status_code=204)


# --- Attachments ---


@router.post("/tickets/{ticket_id}/attachments", status_code=201)
async def add_attachment(
    ticket_id: uuid.UUID,
    caller: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    comment_id: uuid.UUID | None = None,
    replaces_attachment_id: uuid.UUID | None = None,
) -> schemas.AttachmentOut:
    role = await _role(session, caller)
    attachment = await service.add_attachment(
        session, caller, role, ticket_id, file, comment_id, replaces_attachment_id
    )
    return schemas.AttachmentOut.model_validate(attachment)


@router.get("/attachments/{attachment_id}")
async def download_attachment(
    attachment_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> FileResponse:
    role = await _role(session, caller)
    attachment = await service.get_attachment_file(session, caller, role, attachment_id)
    return FileResponse(
        attachment.storage_path, media_type=attachment.mime_type, filename=attachment.file_name
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    attachment_id: uuid.UUID, caller: StaffUser, session: SessionDep
) -> Response:
    role = await _role(session, caller)
    await service.delete_attachment(session, caller, role, attachment_id)
    return Response(status_code=204)


# --- Tags ---


@router.get("/tags")
async def list_tags(caller: CurrentUser, session: SessionDep) -> list[schemas.TagOut]:
    return [schemas.TagOut.model_validate(t) for t in await service.list_tags(session)]


@router.post("/tags", status_code=201)
async def create_tag(
    body: schemas.TagCreate, caller: StaffUser, session: SessionDep
) -> schemas.TagOut:
    return schemas.TagOut.model_validate(await service.create_tag(session, body.name))


@router.post("/tickets/{ticket_id}/tags")
async def attach_tag(
    ticket_id: uuid.UUID, body: schemas.TagAttach, caller: StaffUser, session: SessionDep
) -> schemas.TicketOut:
    role = await _role(session, caller)
    return schemas.TicketOut.model_validate(
        await service.attach_tag(session, caller, role, ticket_id, body.tag_id)
    )
