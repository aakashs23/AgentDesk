"""RBAC primitives (Implementation Plan, Phase 3; rules from Document 05 §6–7).

Every later endpoint reuses these — never inline a role check.
"""

import uuid
from typing import Annotated

import sqlalchemy as sa
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token
from app.db import get_session
from app.models import Role, User

_bearer = HTTPBearer(auto_error=False)

# The four roles are fixed vocabulary seeded by migration 0001 — cache id→name once
_role_names: dict[uuid.UUID, str] = {}


async def role_name(session: AsyncSession, role_id: uuid.UUID) -> str:
    if role_id not in _role_names:
        for role in (await session.execute(sa.select(Role))).scalars():
            _role_names[role.id] = role.name
    return _role_names[role_id]


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    claims = decode_access_token(creds.credentials) if creds else None
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Fresh DB read, not the JWT claims: deactivation applies immediately and a role
    # change takes effect on the next request (App Flow Doc 03, §24)
    user = await session.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def require_role(*allowed: str):
    async def dependency(user: CurrentUser, session: SessionDep) -> User:
        if await role_name(session, user.role_id) not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return dependency


def scope_tickets_to_caller(user: User, role: str, tickets, queues, users):
    """Boolean criterion limiting a tickets query to what the caller may see (Doc 05 §6).

    `tickets`/`queues`/`users` are the ORM models (Phase 4 passes the real ones), so
    this stays the single place ticket visibility is defined.
    """
    if role == "admin":
        return sa.true()
    if role == "requester":
        return tickets.requester_id == user.id
    team_queues = sa.select(queues.id).where(queues.team_id == user.team_id)
    if role == "agent":
        return sa.or_(tickets.assignee_id == user.id, tickets.queue_id.in_(team_queues))
    if role == "team_lead":
        team_members = sa.select(users.id).where(users.team_id == user.team_id)
        return sa.or_(tickets.queue_id.in_(team_queues), tickets.assignee_id.in_(team_members))
    return sa.false()
