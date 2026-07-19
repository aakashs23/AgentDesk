"""Shared test client.

One session-scoped TestClient for every test: asyncpg pool connections are bound
to the event loop they were created on, so each test module spinning up its own
client (= its own loop) would poison the shared engine pool.
"""

import pytest
from fastapi.testclient import TestClient

from app.auth import router as auth_router
from app.config import get_settings
from app.main import app
from app.tickets import router as tickets_router


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    # Attachment files land in a throwaway dir, not the repo working tree
    get_settings().attachment_dir = str(tmp_path_factory.mktemp("attachments"))

    # The suite logs in far more often than a real client from one IP — disable limits
    async def no_limit():
        return None

    for limiter in (
        auth_router.login_limiter,
        auth_router.register_limiter,
        auth_router.reset_limiter,
        tickets_router.create_limiter,
    ):
        app.dependency_overrides[limiter] = no_limit
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
