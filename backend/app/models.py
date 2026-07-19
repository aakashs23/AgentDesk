"""ORM models — columns mirror Backend Schema Document 05 exactly (Alembic owns DDL).

Only tables used by implemented phases appear here; later phases add theirs.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Identity, Integer, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class Role(SQLModel, table=True):
    __tablename__ = "roles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class Team(SQLModel, table=True):
    __tablename__ = "teams"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str
    password_hash: str
    full_name: str
    role_id: uuid.UUID = Field(foreign_key="roles.id")
    team_id: uuid.UUID | None = Field(default=None, foreign_key="teams.id")
    is_active: bool = True
    email_verified_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    notification_preferences: dict = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    theme_preference: str = "system"
    last_login_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    token_hash: str
    user_agent: str | None = None
    ip_address: str | None = None
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class PasswordResetToken(SQLModel, table=True):
    __tablename__ = "password_reset_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    token_hash: str
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    used_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class EmailVerificationToken(SQLModel, table=True):
    __tablename__ = "email_verification_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id")
    token_hash: str
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    used_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


# --- Classification & Configuration (Phase 4 reads these; admin CRUD lands later) ---


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    parent_id: uuid.UUID | None = Field(default=None, foreign_key="categories.id")
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class Priority(SQLModel, table=True):
    __tablename__ = "priorities"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    rank: int
    color_hex: str
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class Queue(SQLModel, table=True):
    __tablename__ = "queues"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    team_id: uuid.UUID | None = Field(default=None, foreign_key="teams.id")
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class SlaPolicy(SQLModel, table=True):
    __tablename__ = "sla_policies"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    category_id: uuid.UUID | None = Field(default=None, foreign_key="categories.id")
    priority_id: uuid.UUID = Field(foreign_key="priorities.id")
    response_minutes: int
    resolution_minutes: int
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


# --- Ticket Core (Document 05, "Ticket Core") ---


class Ticket(SQLModel, table=True):
    __tablename__ = "tickets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    display_id: int | None = Field(
        default=None, sa_column=Column(Integer, Identity(), unique=True, nullable=False)
    )
    subject: str
    description: str
    requester_id: uuid.UUID = Field(foreign_key="users.id")
    assignee_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    category_id: uuid.UUID | None = Field(default=None, foreign_key="categories.id")
    priority_id: uuid.UUID | None = Field(default=None, foreign_key="priorities.id")
    queue_id: uuid.UUID | None = Field(default=None, foreign_key="queues.id")
    status: str = "new"
    channel: str
    source_email_message_id: str | None = None
    response_due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    resolution_due_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    closed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    reopened_count: int = 0
    merged_into_ticket_id: uuid.UUID | None = Field(default=None, foreign_key="tickets.id")
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class Comment(SQLModel, table=True):
    __tablename__ = "comments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id")
    author_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    body: str
    is_internal: bool = False
    is_ai_generated: bool = False
    ai_confidence: float | None = Field(default=None, sa_type=Numeric(5, 2))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))
    updated_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class CommentMention(SQLModel, table=True):
    __tablename__ = "comment_mentions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    comment_id: uuid.UUID = Field(foreign_key="comments.id")
    mentioned_user_id: uuid.UUID = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class Attachment(SQLModel, table=True):
    __tablename__ = "attachments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id")
    comment_id: uuid.UUID | None = Field(default=None, foreign_key="comments.id")
    uploader_id: uuid.UUID = Field(foreign_key="users.id")
    file_name: str
    storage_path: str
    mime_type: str
    size_bytes: int
    version: int = 1
    replaced_by_attachment_id: uuid.UUID | None = Field(default=None, foreign_key="attachments.id")
    deleted_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class TicketTag(SQLModel, table=True):
    __tablename__ = "ticket_tags"

    ticket_id: uuid.UUID = Field(foreign_key="tickets.id", primary_key=True)
    tag_id: uuid.UUID = Field(foreign_key="tags.id", primary_key=True)
    added_by: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


# --- Governance (Document 05, "Governance") ---


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_type: str
    entity_id: uuid.UUID
    actor_id: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    action: str
    before_state: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    after_state: dict | None = Field(default=None, sa_column=Column(JSONB, nullable=True))
    created_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))


class TicketStatusHistory(SQLModel, table=True):
    __tablename__ = "ticket_status_history"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id")
    old_status: str | None = None
    new_status: str
    changed_by: uuid.UUID | None = Field(default=None, foreign_key="users.id")
    changed_at: datetime = Field(default_factory=_now, sa_type=DateTime(timezone=True))
