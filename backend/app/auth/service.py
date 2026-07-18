"""Auth/users business logic — consumed by the thin routers in this module."""

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import security
from app.auth.deps import role_name
from app.auth.schemas import UserCreate, UserOut, UserUpdate
from app.config import get_settings
from app.models import EmailVerificationToken, PasswordResetToken, RefreshToken, Role, Team, User
from app.notifications import mailer

SELF_EDITABLE_FIELDS = {"full_name", "theme_preference", "notification_preferences"}


def _now() -> datetime:
    return datetime.now(UTC)


async def to_user_out(session: AsyncSession, user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=await role_name(session, user.role_id),
        team_id=user.team_id,
        is_active=user.is_active,
        email_verified=user.email_verified_at is not None,
        theme_preference=user.theme_preference,
    )


async def _user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(sa.select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _role_by_name(session: AsyncSession, name: str) -> Role:
    result = await session.execute(sa.select(Role).where(Role.name == name))
    role = result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=422, detail=f"Unknown role: {name}")
    return role


def _send_link_email(to: str, subject: str, intro: str, path: str, raw_token: str) -> None:
    link = f"{get_settings().frontend_origin}/{path}?token={raw_token}"
    mailer.send_email(to, subject, f"{intro}\n\n{link}\n")


async def _issue_refresh(
    session: AsyncSession, user: User, user_agent: str | None, ip: str | None
) -> str:
    raw = security.new_raw_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            user_agent=user_agent,
            ip_address=ip,
            expires_at=_now() + timedelta(days=security.REFRESH_TOKEN_DAYS),
        )
    )
    return raw


async def _revoke_all_refresh(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        sa.update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


# --- Login / tokens ---


async def login(
    session: AsyncSession, email: str, password: str, user_agent: str | None, ip: str | None
) -> tuple[str, str, UserOut]:
    user = await _user_by_email(session, email)
    if user is None or not security.verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Email not verified")
    user.last_login_at = _now()
    access = security.create_access_token(
        user.id, await role_name(session, user.role_id), user.team_id
    )
    raw_refresh = await _issue_refresh(session, user, user_agent, ip)
    user_out = await to_user_out(session, user)
    await session.commit()
    return access, raw_refresh, user_out


async def rotate_refresh(session: AsyncSession, raw_token: str) -> tuple[str, str]:
    result = await session.execute(
        sa.select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(raw_token))
    )
    token = result.scalar_one_or_none()
    if token is None or token.revoked_at is not None or token.expires_at < _now():
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    token.revoked_at = _now()  # rotation: each refresh token is single-use
    access = security.create_access_token(
        user.id, await role_name(session, user.role_id), user.team_id
    )
    new_raw = await _issue_refresh(session, user, token.user_agent, token.ip_address)
    await session.commit()
    return access, new_raw


async def logout(session: AsyncSession, raw_token: str) -> None:
    await session.execute(
        sa.update(RefreshToken)
        .where(
            RefreshToken.token_hash == security.hash_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    await session.commit()


# --- Registration & email verification (App Flow Doc 03 §4, requester path) ---


async def register_requester(
    session: AsyncSession, email: str, password: str, full_name: str
) -> UserOut:
    if await _user_by_email(session, email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    role = await _role_by_name(session, "requester")
    user = User(
        email=email,
        password_hash=security.hash_password(password),
        full_name=full_name,
        role_id=role.id,
    )
    session.add(user)
    await session.flush()
    raw = security.new_raw_token()
    session.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            expires_at=_now() + timedelta(hours=security.VERIFY_TOKEN_HOURS),
        )
    )
    user_out = await to_user_out(session, user)
    await session.commit()
    _send_link_email(
        email, "Verify your AgentDesk email", "Confirm your email address:", "verify-email", raw
    )
    return user_out


async def verify_email(session: AsyncSession, raw_token: str) -> None:
    result = await session.execute(
        sa.select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == security.hash_token(raw_token)
        )
    )
    token = result.scalar_one_or_none()
    if token is None or token.used_at is not None or token.expires_at < _now():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user = await session.get(User, token.user_id)
    token.used_at = _now()
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    await session.commit()


# --- Password reset (also completes the invite flow, App Flow Doc 03 §24) ---


async def request_password_reset(session: AsyncSession, email: str) -> None:
    user = await _user_by_email(session, email)
    if user is None or not user.is_active:
        return  # always 202 — no account enumeration
    raw = security.new_raw_token()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            expires_at=_now() + timedelta(minutes=security.RESET_TOKEN_MINUTES),
        )
    )
    await session.commit()
    _send_link_email(
        email, "Reset your AgentDesk password", "Set a new password:", "reset-password", raw
    )


async def confirm_password_reset(session: AsyncSession, raw_token: str, new_password: str) -> None:
    result = await session.execute(
        sa.select(PasswordResetToken).where(
            PasswordResetToken.token_hash == security.hash_token(raw_token)
        )
    )
    token = result.scalar_one_or_none()
    if token is None or token.used_at is not None or token.expires_at < _now():
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    user = await session.get(User, token.user_id)
    token.used_at = _now()  # single-use
    user.password_hash = security.hash_password(new_password)
    user.updated_at = _now()
    if user.email_verified_at is None:
        # Invite flow: following the emailed link proves ownership of the address
        user.email_verified_at = _now()
    await _revoke_all_refresh(session, user.id)  # TRD §9: revoke on password reset
    await session.commit()


# --- Users CRUD (permissions matrix, Document 05 §7) ---


async def invite_user(session: AsyncSession, body: UserCreate) -> UserOut:
    if await _user_by_email(session, body.email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")
    role = await _role_by_name(session, body.role)
    if body.team_id is not None and await session.get(Team, body.team_id) is None:
        raise HTTPException(status_code=422, detail="Unknown team")
    user = User(
        email=body.email,
        # Unusable until the invite is accepted — the raw value is never known to anyone
        password_hash=security.hash_password(security.new_raw_token()),
        full_name=body.full_name,
        role_id=role.id,
        team_id=body.team_id,
    )
    session.add(user)
    await session.flush()
    raw = security.new_raw_token()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=security.hash_token(raw),
            expires_at=_now() + timedelta(days=security.INVITE_TOKEN_DAYS),
        )
    )
    user_out = await to_user_out(session, user)
    await session.commit()
    _send_link_email(
        body.email,
        "You've been invited to AgentDesk",
        "Set your password to activate your account:",
        "accept-invite",
        raw,
    )
    return user_out


async def _get_user_or_404(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


async def list_users(
    session: AsyncSession,
    caller: User,
    caller_role: str,
    role: str | None,
    team_id: uuid.UUID | None,
) -> list[UserOut]:
    stmt = sa.select(User).order_by(User.created_at)
    if caller_role == "team_lead":  # team leads see their own team only (Doc 05 §6)
        stmt = stmt.where(User.team_id == caller.team_id)
    if team_id is not None:
        stmt = stmt.where(User.team_id == team_id)
    if role is not None:
        stmt = stmt.where(User.role_id == (await _role_by_name(session, role)).id)
    users = (await session.execute(stmt)).scalars().all()
    return [await to_user_out(session, u) for u in users]


async def get_user_checked(
    session: AsyncSession, caller: User, caller_role: str, user_id: uuid.UUID
) -> UserOut:
    target = await _get_user_or_404(session, user_id)
    allowed = (
        caller_role == "admin"
        or caller.id == target.id
        or (caller_role == "team_lead" and target.team_id == caller.team_id)
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Not permitted")
    return await to_user_out(session, target)


async def update_user(
    session: AsyncSession, caller: User, caller_role: str, user_id: uuid.UUID, body: UserUpdate
) -> UserOut:
    target = await _get_user_or_404(session, user_id)
    fields = body.model_fields_set
    if caller_role != "admin":
        if caller.id != target.id or not fields <= SELF_EDITABLE_FIELDS:
            raise HTTPException(status_code=403, detail="Not permitted")
    if body.full_name is not None:
        target.full_name = body.full_name
    if body.theme_preference is not None:
        target.theme_preference = body.theme_preference
    if body.notification_preferences is not None:
        target.notification_preferences = body.notification_preferences
    if "role" in fields:
        target.role_id = (await _role_by_name(session, body.role)).id
    if "team_id" in fields:
        if body.team_id is not None and await session.get(Team, body.team_id) is None:
            raise HTTPException(status_code=422, detail="Unknown team")
        target.team_id = body.team_id
    if "is_active" in fields:
        target.is_active = body.is_active
        if not body.is_active:
            await _revoke_all_refresh(session, target.id)
    target.updated_at = _now()
    user_out = await to_user_out(session, target)
    await session.commit()
    return user_out


async def deactivate_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    target = await _get_user_or_404(session, user_id)
    target.is_active = False
    target.updated_at = _now()
    await _revoke_all_refresh(session, target.id)
    await session.commit()
