"""Request/response bodies for auth and users endpoints (TRD Section 3)."""

import uuid

from pydantic import BaseModel, Field

from app.auth.security import MAX_PASSWORD_BYTES
from app.validators import BoundedJson, NormalisedEmail


class UserOut(BaseModel):
    """Public user shape — never includes password_hash or token fields (Doc 05 §8)."""

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    team_id: uuid.UUID | None
    is_active: bool
    email_verified: bool
    theme_preference: str


class LoginRequest(BaseModel):
    email: NormalisedEmail
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str  # rotation: the old token is revoked, this replaces it


class LogoutRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    email: NormalisedEmail
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)
    full_name: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    email: NormalisedEmail


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)


class VerifyEmailRequest(BaseModel):
    token: str


class PasswordChangeRequest(BaseModel):
    """Authenticated change from Account Settings — proves ownership with the
    current password instead of an emailed reset token."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)


class UserCreate(BaseModel):
    """Admin-provisioned account (invite flow, App Flow Doc 03 §24)."""

    email: NormalisedEmail
    full_name: str = Field(min_length=1)
    role: str  # requester / agent / team_lead / admin
    team_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    theme_preference: str | None = None
    notification_preferences: BoundedJson | None = None
    # Admin-only fields (403 for anyone else)
    role: str | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None
