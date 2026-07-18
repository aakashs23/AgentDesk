"""Request/response bodies for auth and users endpoints (TRD Section 3)."""

import uuid

from pydantic import BaseModel, EmailStr, Field


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
    email: EmailStr
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
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class VerifyEmailRequest(BaseModel):
    token: str


class UserCreate(BaseModel):
    """Admin-provisioned account (invite flow, App Flow Doc 03 §24)."""

    email: EmailStr
    full_name: str = Field(min_length=1)
    role: str  # requester / agent / team_lead / admin
    team_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    full_name: str | None = None
    theme_preference: str | None = None
    notification_preferences: dict | None = None
    # Admin-only fields (403 for anyone else)
    role: str | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None
