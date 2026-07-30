"""AgentDesk API — application shell (Implementation Plan, Phase 2).

Feature routers plug in here as their phases land (auth in Phase 3, tickets in
Phase 4, ...); each module under app/ owns its bounded concern per TRD Section 2.
"""

import asyncio
import contextlib
import logging
import time

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.admin_config.router import router as admin_router
from app.ai.router import router as ai_router
from app.auth.router import router as auth_router
from app.auth.users_router import router as users_router
from app.config import get_settings
from app.db import engine
from app.log import setup_logging
from app.notifications.router import router as notifications_router
from app.reporting.router import router as reporting_router
from app.search.router import router as search_router
from app.sla import monitor
from app.tickets.router import router as tickets_router
from app.webhooks.router import router as webhooks_router

setup_logging()
logger = logging.getLogger("agentdesk")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # SLA monitor loop (Phase 6, TRD §11); interval 0 disables it
    interval = get_settings().sla_scan_interval_seconds
    task = asyncio.create_task(monitor.run_forever(interval)) if interval > 0 else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="AgentDesk API", lifespan=lifespan)

# All feature endpoints are prefixed /api/v1 (TRD Section 3); health stays unprefixed
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(tickets_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")
app.include_router(reporting_router, prefix="/api/v1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            "client": request.client.host if request.client else None,
        },
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Identical to FastAPI's default, except that a body nested deeply enough to
    # exhaust the recursion limit blows up *inside* the default handler while it
    # encodes the offending value back under `input` — turning a 422 into a 500.
    # Only that case loses `input`; every ordinary error keeps it.
    errors = exc.errors()
    try:
        detail = jsonable_encoder(errors)
    except RecursionError:
        detail = jsonable_encoder([{k: v for k, v in e.items() if k != "input"} for e in errors])
    return JSONResponse(status_code=422, content={"detail": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full stack trace stays server-side; the client gets a generic 500
    logger.exception(
        "unhandled exception",
        exc_info=exc,
        extra={"method": request.method, "path": request.url.path},
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readiness check failed: database unreachable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return JSONResponse(content={"status": "ready"})
