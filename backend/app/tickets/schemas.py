"""Request/response bodies for the ticket domain (TRD Section 3)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1)
    description: str = Field(min_length=1)
    channel: str = "portal"  # portal/email/chat (Document 05)
    category_id: uuid.UUID | None = None  # the ticket form's optional category dropdown


class TicketUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    # Classification fields — staff only (Doc 05 §6)
    category_id: uuid.UUID | None = None
    priority_id: uuid.UUID | None = None
    queue_id: uuid.UUID | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_id: int
    subject: str
    description: str
    requester_id: uuid.UUID
    assignee_id: uuid.UUID | None
    category_id: uuid.UUID | None
    priority_id: uuid.UUID | None
    queue_id: uuid.UUID | None
    status: str
    channel: str
    response_due_at: datetime | None
    resolution_due_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopened_count: int
    merged_into_ticket_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # "formatted at the app layer" per Document 05 tickets.display_id
    def ref(self) -> str:
        return f"AGT-{self.display_id}"


class StatusChange(BaseModel):
    status: str


class StatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    old_status: str | None
    new_status: str
    changed_by: uuid.UUID | None
    changed_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)
    is_internal: bool = False


class CommentUpdate(BaseModel):
    body: str = Field(min_length=1)


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    is_internal: bool
    is_ai_generated: bool
    created_at: datetime
    updated_at: datetime | None


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    comment_id: uuid.UUID | None
    uploader_id: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int
    version: int
    replaced_by_attachment_id: uuid.UUID | None
    created_at: datetime


class TagCreate(BaseModel):
    name: str = Field(min_length=1)


class TagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str


class TagAttach(BaseModel):
    tag_id: uuid.UUID


class AssignRequest(BaseModel):
    assignee_id: uuid.UUID | None = None
    queue_id: uuid.UUID | None = None


class MergeRequest(BaseModel):
    target_ticket_id: uuid.UUID  # the primary this ticket merges into


class SplitPart(BaseModel):
    subject: str = Field(min_length=1)
    description: str = Field(min_length=1)


class SplitRequest(BaseModel):
    subtickets: list[SplitPart] = Field(min_length=1)
