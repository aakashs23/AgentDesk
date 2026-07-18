"""Users CRUD (TRD Section 3, Users group; permissions per Document 05 §7)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.auth import schemas, service
from app.auth.deps import CurrentUser, SessionDep, require_role, role_name
from app.models import User

router = APIRouter(prefix="/users", tags=["users"])

AdminUser = Annotated[User, Depends(require_role("admin"))]


@router.get("")
async def list_users(
    caller: Annotated[User, Depends(require_role("admin", "team_lead"))],
    session: SessionDep,
    role: str | None = None,
    team_id: uuid.UUID | None = None,
) -> list[schemas.UserOut]:
    caller_role = await role_name(session, caller.role_id)
    return await service.list_users(session, caller, caller_role, role, team_id)


@router.get("/{user_id}")
async def get_user(user_id: uuid.UUID, caller: CurrentUser, session: SessionDep) -> schemas.UserOut:
    caller_role = await role_name(session, caller.role_id)
    return await service.get_user_checked(session, caller, caller_role, user_id)


@router.post("", status_code=201)
async def create_user(
    body: schemas.UserCreate, _: AdminUser, session: SessionDep
) -> schemas.UserOut:
    return await service.invite_user(session, body)


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: schemas.UserUpdate, caller: CurrentUser, session: SessionDep
) -> schemas.UserOut:
    caller_role = await role_name(session, caller.role_id)
    return await service.update_user(session, caller, caller_role, user_id, body)


@router.delete("/{user_id}", status_code=204)
async def deactivate_user(user_id: uuid.UUID, _: AdminUser, session: SessionDep) -> Response:
    await service.deactivate_user(session, user_id)
    return Response(status_code=204)
