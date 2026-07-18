"""Auth endpoints (TRD Section 3, Authentication group)."""

from fastapi import APIRouter, Depends, Request, Response

from app.auth import schemas, service
from app.auth.deps import CurrentUser, SessionDep
from app.rate_limit import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# Named so tests can disable them via app.dependency_overrides
login_limiter = rate_limit(10)
register_limiter = rate_limit(5)
reset_limiter = rate_limit(5)


@router.post("/login", dependencies=[Depends(login_limiter)])
async def login(
    body: schemas.LoginRequest, request: Request, session: SessionDep
) -> schemas.TokenResponse:
    access, refresh, user = await service.login(
        session,
        body.email,
        body.password,
        request.headers.get("user-agent"),
        request.client.host if request.client else None,
    )
    return schemas.TokenResponse(access_token=access, refresh_token=refresh, user=user)


@router.post("/refresh")
async def refresh(body: schemas.RefreshRequest, session: SessionDep) -> schemas.RefreshResponse:
    access, new_refresh = await service.rotate_refresh(session, body.refresh_token)
    return schemas.RefreshResponse(access_token=access, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(body: schemas.LogoutRequest, _: CurrentUser, session: SessionDep) -> Response:
    await service.logout(session, body.refresh_token)
    return Response(status_code=204)


@router.post("/register", status_code=201, dependencies=[Depends(register_limiter)])
async def register(body: schemas.RegisterRequest, session: SessionDep) -> schemas.UserOut:
    return await service.register_requester(session, body.email, body.password, body.full_name)


@router.post("/password-reset/request", status_code=202, dependencies=[Depends(reset_limiter)])
async def password_reset_request(
    body: schemas.PasswordResetRequest, session: SessionDep
) -> dict[str, str]:
    await service.request_password_reset(session, body.email)
    return {"detail": "If the account exists, a reset email has been sent"}


@router.post("/password-reset/confirm")
async def password_reset_confirm(
    body: schemas.PasswordResetConfirm, session: SessionDep
) -> dict[str, str]:
    await service.confirm_password_reset(session, body.token, body.new_password)
    return {"detail": "Password updated"}


@router.post("/verify-email")
async def verify_email(body: schemas.VerifyEmailRequest, session: SessionDep) -> dict[str, str]:
    await service.verify_email(session, body.token)
    return {"detail": "Email verified"}
