"""Suite-wide fixtures and one-time test-database provisioning.

Running `pytest` from a cold checkout must not need manual setup, so this module
does three things before anything imports the app:

1. Points `DATABASE_URL` at a *separate* database whose name ends in `_test`, so
   a stray run can never touch the dev/production database.
2. Creates that database (plus the vector/pgcrypto/pg_trgm extensions), runs
   `alembic upgrade head`, and seeds the demo dataset — all idempotent.
3. Builds one session-scoped TestClient, because asyncpg pool connections are
   bound to the event loop that created them: a client per module means a loop
   per module, which poisons the shared engine pool.

Isolation model: these are API-level integration tests against a live Postgres,
so there is no per-test transaction rollback (the app opens its own sessions per
request, outside any transaction the test could roll back). Tests isolate by
generating unique data instead — see `helpers.factories`, whose every name,
email and subject carries a per-call random suffix.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _dotenv_value(key: str) -> str | None:
    for env_file in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if not env_file.is_file():
            continue
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return None


def _test_database_url() -> str:
    """The dev URL with `_test` appended to the database name.

    `TEST_DATABASE_URL` overrides it outright (CI points this at its own server).
    """
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get("DATABASE_URL") or _dotenv_value("DATABASE_URL")
    if not base:
        base = "postgresql+asyncpg://agentdesk:agentdesk@localhost:5432/agentdesk"
    base, _, name = base.rpartition("/")
    name, sep, query = name.partition("?")
    if not name.endswith("_test"):
        name += "_test"
    return f"{base}/{name}{sep}{query}"


DATABASE_URL = _test_database_url()

# Refuse to run against anything that is not an explicitly-named test database.
if not DATABASE_URL.rpartition("/")[2].partition("?")[0].endswith("_test"):
    raise RuntimeError(
        f"Refusing to run the test suite against {DATABASE_URL!r}: "
        "the database name must end in '_test'."
    )

# Must be set before app.config caches Settings and app.db builds the engine.
os.environ["DATABASE_URL"] = DATABASE_URL

import faulthandler  # noqa: E402

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.auth import router as auth_router  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.tickets import router as tickets_router  # noqa: E402

SYNC_URL = DATABASE_URL.replace("+asyncpg", "+psycopg2")
EXTENSIONS = ("vector", "pgcrypto", "pg_trgm")


def _provision_database() -> None:
    """Create + migrate + seed the test database. Idempotent."""
    admin_url = SYNC_URL.rpartition("/")[0] + "/postgres"
    db_name = DATABASE_URL.rpartition("/")[2].partition("?")[0]

    admin_engine = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            sa.text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
        ).first()
        if not exists:
            conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    admin_engine.dispose()

    engine = sa.create_engine(SYNC_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        for ext in EXTENSIONS:
            conn.execute(sa.text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
        migrated = conn.execute(sa.text("SELECT to_regclass('public.tickets')")).scalar()
    engine.dispose()

    env = {**os.environ, "DATABASE_URL": DATABASE_URL}
    if not migrated:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
        )
    subprocess.run(
        [sys.executable, "-m", "scripts.seed"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
        capture_output=True,
    )


_provision_database()


@pytest.fixture(autouse=True)
def _hang_watchdog():
    # ponytail: a hung test previously blocked CI for 10+ minutes with zero
    # diagnostic output. TestClient runs the app on its own portal thread, so a
    # plain SIGALRM in the main thread wouldn't show where that thread is stuck —
    # dump_traceback_later dumps every thread's stack, then hard-exits so CI
    # fails fast with the culprit instead of running out the job timeout.
    faulthandler.dump_traceback_later(60, exit=True, file=sys.stderr)
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


@pytest.fixture(scope="session")
def db():
    """Synchronous engine for asserting directly on persisted rows."""
    engine = sa.create_engine(SYNC_URL)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def tokens(client):
    """Access token per seeded demo role."""
    from tests.helpers.auth import seed_tokens

    return seed_tokens(client)


@pytest.fixture(scope="session")
def user_ids(db):
    """Seeded demo user id per role.

    Matches the four seed addresses exactly: other tests also create accounts
    under @agentdesk.dev, so a LIKE would return whichever one sorted last.
    """
    from tests.helpers.auth import SEED_USERS

    with db.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT email, id FROM users WHERE email = ANY(:emails)"),
            {"emails": list(SEED_USERS.values())},
        ).all()
    by_email = {email: str(uid) for email, uid in rows}
    return {role: by_email[email] for role, email in SEED_USERS.items()}


@pytest.fixture
def outbox(monkeypatch):
    """Capture emails the app would send instead of logging them."""
    from app.notifications import mailer

    sent: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mailer, "send_email", lambda to, s, b: sent.append((to, s, b)))
    # notifications.service imported `mailer` as a module, so patching the
    # attribute above covers both call sites.
    return sent


@pytest.fixture(autouse=True)
def _no_ai_pipeline(request, monkeypatch):
    """Keep the background AI pipeline out of tests that do not opt into it.

    Ticket creation schedules `pipeline.run_for_ticket` as a BackgroundTask; it
    no-ops without an API key, but stubbing it keeps timing deterministic.
    Tests that exercise the pipeline are marked `ai` and opt out.
    """
    if request.node.get_closest_marker("ai"):
        return
    from app.tickets import router as tickets_router_mod

    async def noop(_ticket_id):
        return None

    monkeypatch.setattr(tickets_router_mod.pipeline, "run_for_ticket", noop)
