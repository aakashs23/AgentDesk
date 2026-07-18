"""Shared test client.

One session-scoped TestClient for every test: asyncpg pool connections are bound
to the event loop they were created on, so each test module spinning up its own
client (= its own loop) would poison the shared engine pool.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import router as auth_router
from app.main import app


@pytest.fixture(scope="session")
def client():
    # The suite logs in far more often than a real client from one IP — disable limits
    async def no_limit():
        return None

    for limiter in (
        auth_router.login_limiter,
        auth_router.register_limiter,
        auth_router.reset_limiter,
    ):
        app.dependency_overrides[limiter] = no_limit
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
