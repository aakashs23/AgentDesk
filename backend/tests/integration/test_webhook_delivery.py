"""Outbound webhook delivery: signing, retries, and the delivery record.

`dispatch` is fire-and-forget, so these drive `_deliver_one` / `_run_dispatch`
directly on the app's event loop with the HTTP client stubbed. No network is
touched — the point is the retry/backoff logic and what lands in
`webhook_deliveries`, not httpx itself.
"""

import hashlib
import hmac
import json

import pytest
import sqlalchemy as sa

from app.db import _session_factory
from app.models import Webhook
from app.webhooks import service as webhooks
from tests.helpers import factories as f
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeClient:
    """Stands in for httpx.AsyncClient, recording every POST it is given.

    `statuses` is a shared list, not a per-instance copy: `_deliver_one` opens a
    *new* client for each retry attempt, so a per-instance copy would replay the
    first status forever and no retry sequence could ever be tested.
    """

    def __init__(self, statuses, calls, error=None, **_kwargs):
        self._statuses = statuses
        self._calls = calls
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, content=None, headers=None):
        self._calls.append({"url": url, "content": content, "headers": headers})
        if self._error is not None:
            raise self._error
        return FakeResponse(self._statuses.pop(0) if self._statuses else 200)


@pytest.fixture
def stub_transport(monkeypatch):
    """Install a fake client and return the list it records calls into."""
    calls: list[dict] = []

    def install(statuses=(200,), error=None):
        shared = list(statuses)
        monkeypatch.setattr(webhooks.asyncio, "sleep", _no_sleep)
        monkeypatch.setattr(
            webhooks.httpx,
            "AsyncClient",
            lambda **kwargs: FakeClient(shared, calls, error, **kwargs),
        )
        return calls

    return install


async def _no_sleep(_seconds):
    """Collapse the retry backoff so a 3-attempt test is not a 3-second test."""
    return None


@pytest.fixture
def registered_webhook(client, tokens):
    created = client.post(
        f"{API}/webhooks",
        json={
            "event_type": "ticket_created",
            "target_url": "https://receiver.invalid/hook",
            "secret": "shared-secret",
        },
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    yield created.json()
    client.delete(f"{API}/webhooks/{created.json()['id']}", headers=auth(tokens["admin"]))


def _deliver(client, webhook_id, event="ticket_created", payload=None):
    async def go():
        async with _session_factory() as session:
            webhook = await session.get(Webhook, webhook_id)
            await webhooks._deliver_one(
                session, webhook, event, payload or {"event": event, "ticket_id": "x"}
            )
            await session.commit()

    return f.run_on_app_loop(client, go)


def _deliveries(db, webhook_id):
    with db.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                sa.text(
                    "SELECT response_status, attempt_count, delivered_at FROM webhook_deliveries "
                    "WHERE webhook_id = :w ORDER BY created_at"
                ),
                {"w": webhook_id},
            ).mappings()
        ]


# --- Signing ---


def test_the_payload_is_signed_with_the_webhooks_own_secret(
    client, db, registered_webhook, stub_transport
):
    calls = stub_transport(statuses=[200])
    payload = {"event": "ticket_created", "ticket_id": "abc"}
    _deliver(client, registered_webhook["id"], payload=payload)

    assert len(calls) == 1, calls
    sent = calls[0]
    expected = "sha256=" + hmac.new(b"shared-secret", sent["content"], hashlib.sha256).hexdigest()
    assert sent["headers"]["X-AgentDesk-Signature"] == expected, "the signature does not verify"
    assert sent["headers"]["X-AgentDesk-Event"] == "ticket_created"
    assert sent["headers"]["Content-Type"] == "application/json"
    assert json.loads(sent["content"]) == payload


def test_the_signature_changes_when_the_body_changes(client, registered_webhook, stub_transport):
    """Guards against a constant or body-independent signature."""
    calls = stub_transport(statuses=[200, 200])
    _deliver(client, registered_webhook["id"], payload={"event": "a", "ticket_id": "1"})
    _deliver(client, registered_webhook["id"], payload={"event": "a", "ticket_id": "2"})

    signatures = {c["headers"]["X-AgentDesk-Signature"] for c in calls}
    assert len(signatures) == 2, "the same signature was sent for two different bodies"


def test_sign_matches_a_manually_computed_hmac():
    body = b'{"hello": "world"}'
    expected = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert webhooks.sign("topsecret", body) == f"sha256={expected}"


def test_secrets_round_trip_through_encryption():
    token = webhooks.encrypt_secret("plaintext")
    assert token != "plaintext"
    assert webhooks.decrypt_secret(token) == "plaintext"


# --- Delivery outcomes ---


def test_a_successful_delivery_is_recorded_once(client, db, registered_webhook, stub_transport):
    stub_transport(statuses=[200])
    _deliver(client, registered_webhook["id"])

    rows = _deliveries(db, registered_webhook["id"])
    assert len(rows) == 1, rows
    assert rows[0]["response_status"] == 200
    assert rows[0]["attempt_count"] == 1
    assert rows[0]["delivered_at"] is not None


@pytest.mark.parametrize("status", [500, 502, 404, 400])
def test_a_failing_delivery_is_retried_to_the_attempt_limit(
    client, db, registered_webhook, stub_transport, status
):
    calls = stub_transport(statuses=[status] * webhooks.MAX_ATTEMPTS)
    _deliver(client, registered_webhook["id"])

    assert len(calls) == webhooks.MAX_ATTEMPTS, f"{len(calls)} attempts made"
    rows = _deliveries(db, registered_webhook["id"])
    assert len(rows) == webhooks.MAX_ATTEMPTS
    assert [r["attempt_count"] for r in rows] == list(range(1, webhooks.MAX_ATTEMPTS + 1))
    assert all(r["delivered_at"] is None for r in rows), "a failure was marked delivered"
    assert all(r["response_status"] == status for r in rows)


def test_retrying_stops_as_soon_as_it_succeeds(client, db, registered_webhook, stub_transport):
    calls = stub_transport(statuses=[500, 200, 200])
    _deliver(client, registered_webhook["id"])

    assert len(calls) == 2, f"retrying did not stop after success ({len(calls)} attempts)"
    rows = _deliveries(db, registered_webhook["id"])
    assert [r["response_status"] for r in rows] == [500, 200]
    assert rows[0]["delivered_at"] is None
    assert rows[1]["delivered_at"] is not None


def test_a_transport_error_is_recorded_with_no_status(
    client, db, registered_webhook, stub_transport
):
    """A connection failure must be captured, not lost — `response_status` null."""
    import httpx

    stub_transport(error=httpx.ConnectError("connection refused"))
    _deliver(client, registered_webhook["id"])

    rows = _deliveries(db, registered_webhook["id"])
    assert len(rows) == webhooks.MAX_ATTEMPTS
    assert all(r["response_status"] is None for r in rows)
    assert all(r["delivered_at"] is None for r in rows)


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_any_2xx_counts_as_delivered(client, db, registered_webhook, stub_transport, status):
    stub_transport(statuses=[status])
    _deliver(client, registered_webhook["id"])
    rows = _deliveries(db, registered_webhook["id"])
    assert rows[-1]["delivered_at"] is not None, f"{status} was not treated as delivered"


# --- Fan-out ---


def test_dispatch_only_reaches_webhooks_for_that_event(client, db, tokens, stub_transport):
    calls = stub_transport(statuses=[200] * 10)
    wanted = client.post(
        f"{API}/webhooks",
        json={"event_type": "status_changed", "target_url": "https://wanted.invalid/h"},
        headers=auth(tokens["admin"]),
    ).json()
    other = client.post(
        f"{API}/webhooks",
        json={"event_type": "sla_breached", "target_url": "https://other.invalid/h"},
        headers=auth(tokens["admin"]),
    ).json()
    try:

        async def go():
            await webhooks._run_dispatch("status_changed", {"event": "status_changed"})

        f.run_on_app_loop(client, go)

        urls = {c["url"] for c in calls}
        assert "https://wanted.invalid/h" in urls
        assert "https://other.invalid/h" not in urls, "an unrelated event type was delivered"
    finally:
        for webhook in (wanted, other):
            client.delete(f"{API}/webhooks/{webhook['id']}", headers=auth(tokens["admin"]))


def test_an_inactive_webhook_receives_nothing(client, tokens, stub_transport):
    calls = stub_transport(statuses=[200] * 5)
    created = client.post(
        f"{API}/webhooks",
        json={
            "event_type": "comment_added",
            "target_url": "https://inactive.invalid/h",
            "is_active": False,
        },
        headers=auth(tokens["admin"]),
    ).json()
    try:

        async def go():
            await webhooks._run_dispatch("comment_added", {"event": "comment_added"})

        f.run_on_app_loop(client, go)
        assert not [c for c in calls if c["url"] == "https://inactive.invalid/h"], (
            "an inactive webhook was delivered to"
        )
    finally:
        client.delete(f"{API}/webhooks/{created['id']}", headers=auth(tokens["admin"]))


def test_the_ticket_payload_carries_the_documented_fields(client, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    from types import SimpleNamespace

    row = SimpleNamespace(
        id=ticket["id"],
        display_id=ticket["display_id"],
        subject=ticket["subject"],
        status=ticket["status"],
        priority_id=None,
        assignee_id=None,
    )
    payload = webhooks.ticket_payload("ticket_created", row)
    assert payload == {
        "event": "ticket_created",
        "ticket_id": str(ticket["id"]),
        "display_id": f"AGT-{ticket['display_id']}",
        "subject": ticket["subject"],
        "status": ticket["status"],
        "priority_id": None,
        "assignee_id": None,
    }


def test_a_dispatch_failure_never_escapes_into_the_caller(client, monkeypatch):
    """`dispatch` is fire-and-forget: a broken delivery must not surface as an
    unhandled task exception or break the request that triggered it."""

    async def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(webhooks, "_deliver_one", explode)

    async def go():
        await webhooks._run_dispatch("ticket_created", {"event": "ticket_created"})

    f.run_on_app_loop(client, go)  # must not raise
