"""Shared test client.

One session-scoped TestClient for every test: asyncpg pool connections are bound
to the event loop they were created on, so each test module spinning up its own
client (= its own loop) would poison the shared engine pool.
"""

import faulthandler
import sys

import pytest
from fastapi.testclient import TestClient

from app.auth import router as auth_router
from app.config import get_settings
from app.main import app
from app.tickets import router as tickets_router


@pytest.fixture(autouse=True)
def _hang_watchdog():
    # ponytail: a hung test previously blocked CI for 10+ minutes with zero
    # diagnostic output. TestClient runs the app on its own portal thread, so a
    # plain SIGALRM in the main thread wouldn't show where that thread is stuck —
    # dump_traceback_later dumps every thread's stack, then hard-exits so CI
    # fails fast with the culprit instead of running out the job timeout.
    faulthandler.dump_traceback_later(30, exit=True, file=sys.stderr)
    yield
    faulthandler.cancel_dump_traceback_later()


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    # Attachment files land in a throwaway dir, not the repo working tree
    get_settings().attachment_dir = str(tmp_path_factory.mktemp("attachments"))

    # Never let the suite reach the real Gemini API — tests that exercise the
    # AI pipeline monkeypatch a fake key plus fake gemini functions per test
    get_settings().gemini_api_key = ""

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
