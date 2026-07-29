"""Rate limiting (TRD §10).

The session-wide `client` fixture disables the limiters, because the suite logs
in far more often than any real client would. These tests therefore build their
own app/client so the real dependency is in play, and exercise the limiter
directly for the window behaviour.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import router as auth_router
from app.main import app as real_app
from app.rate_limit import rate_limit
from tests.helpers.auth import API


@pytest.fixture
def limited_client(client):
    """The shared client with the auth limiters temporarily un-overridden.

    Deliberately *not* a second TestClient over the real app: a new client means
    a new event loop, and the asyncpg pool's connections are bound to the loop
    that opened them — a second loop poisons the pool for every later test.
    So this restores the real dependency on the existing client instead.

    Each limiter also gets a fresh bucket dict, because the closure state
    survives across tests and the suite has already spent the allowance.
    """
    limiters = {
        auth_router.login_limiter: rate_limit(10),
        auth_router.register_limiter: rate_limit(5),
        auth_router.reset_limiter: rate_limit(5),
    }
    saved = {key: real_app.dependency_overrides.pop(key, None) for key in limiters}
    for key, fresh in limiters.items():
        real_app.dependency_overrides[key] = fresh
    yield client
    for key, previous in saved.items():
        if previous is None:
            real_app.dependency_overrides.pop(key, None)
        else:
            real_app.dependency_overrides[key] = previous


def test_brute_forcing_the_login_endpoint_is_throttled(limited_client):
    """Ten attempts per minute per client; the eleventh must be refused."""
    statuses = [
        limited_client.post(
            f"{API}/auth/login",
            json={"email": "admin@agentdesk.dev", "password": f"wrong-{i}"},
        ).status_code
        for i in range(15)
    ]
    assert 429 in statuses, f"no throttling after 15 failed logins: {statuses}"
    assert statuses.count(401) <= 10, f"more than 10 attempts got through: {statuses}"
    # Once throttled it stays throttled for the rest of the window.
    assert statuses[-1] == 429


def test_a_throttled_login_does_not_leak_whether_the_password_was_right(limited_client):
    for _ in range(12):
        limited_client.post(
            f"{API}/auth/login", json={"email": "admin@agentdesk.dev", "password": "wrong"}
        )
    correct = limited_client.post(
        f"{API}/auth/login", json={"email": "admin@agentdesk.dev", "password": "Password123!"}
    )
    assert correct.status_code == 429, "throttle bypassed by sending the right password"
    assert "access_token" not in correct.text


def test_registration_is_throttled(limited_client):
    from tests.helpers import factories as f

    statuses = [
        limited_client.post(
            f"{API}/auth/register",
            json={"email": f.unique_email("flood"), "password": "Password123!", "full_name": "F"},
        ).status_code
        for _ in range(9)
    ]
    assert 429 in statuses, f"registration flood was not throttled: {statuses}"


def test_password_reset_requests_are_throttled(limited_client):
    statuses = [
        limited_client.post(
            f"{API}/auth/password-reset/request", json={"email": "admin@agentdesk.dev"}
        ).status_code
        for _ in range(9)
    ]
    assert 429 in statuses, f"reset flood was not throttled: {statuses}"


# --- The limiter primitive itself ---


def test_the_limiter_counts_per_key_not_globally():
    """Two callers must not share one bucket."""
    probe = FastAPI()
    limiter = rate_limit(2)

    @probe.get("/x", dependencies=[Depends(limiter)])
    def endpoint():
        return {"ok": True}

    with TestClient(probe, raise_server_exceptions=False) as c:
        a = {"Authorization": "Bearer caller-a"}
        b = {"Authorization": "Bearer caller-b"}
        assert [c.get("/x", headers=a).status_code for _ in range(3)] == [200, 200, 429]
        # A different caller still has a full allowance.
        assert c.get("/x", headers=b).status_code == 200


def test_the_window_expires_and_the_allowance_returns(monkeypatch):
    probe = FastAPI()
    limiter = rate_limit(2, window_seconds=60)

    @probe.get("/x", dependencies=[Depends(limiter)])
    def endpoint():
        return {"ok": True}

    clock = {"now": 1000.0}
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: clock["now"])

    with TestClient(probe, raise_server_exceptions=False) as c:
        headers = {"Authorization": "Bearer window-test"}
        assert [c.get("/x", headers=headers).status_code for _ in range(3)] == [200, 200, 429]
        clock["now"] += 61
        assert c.get("/x", headers=headers).status_code == 200, "window never reset"


def test_an_anonymous_caller_is_keyed_by_ip():
    """With no Authorization header the bucket falls back to the client host."""
    probe = FastAPI()
    limiter = rate_limit(2)

    @probe.get("/x", dependencies=[Depends(limiter)])
    def endpoint():
        return {"ok": True}

    with TestClient(probe, raise_server_exceptions=False) as c:
        assert [c.get("/x").status_code for _ in range(3)] == [200, 200, 429]
