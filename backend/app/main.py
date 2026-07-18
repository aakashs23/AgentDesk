"""AgentDesk API — application shell (Implementation Plan, Phase 2).

Feature routers plug in here as their phases land (auth in Phase 3, tickets in
Phase 4, ...); each module under app/ owns its bounded concern per TRD Section 2.
"""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.auth.router import router as auth_router
from app.auth.users_router import router as users_router
from app.config import get_settings
from app.db import engine
from app.log import setup_logging

setup_logging()
logger = logging.getLogger("agentdesk")

app = FastAPI(title="AgentDesk API")

# All feature endpoints are prefixed /api/v1 (TRD Section 3); health stays unprefixed
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")

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
