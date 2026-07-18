"""ORM models — columns mirror Backend Schema Document 05 exactly (Alembic owns DDL).

Only tables used by implemented phases appear here; later phases add theirs.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime
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
