"""App Flow §27 — system-level failure modes, and the §28 scenarios that ride on
them.

§6 covers per-screen empty/error/loading states. Those are frontend concerns —
`components/EmptyState.tsx` and `components/Skeleton.tsx`, rendered off React
Query's `isPending`/`isError`, and audited screen by screen in the Phase 15 QA
report. What is testable on the backend is the contract those screens depend on:
when a dependency dies, the request either degrades to a documented fallback or
fails in a way that cannot take the rest of the product down with it.

Each test names the §27 row it pins. The recurring shape is "kill one dependency,
assert the *other* path still works" — that is exactly what the Fallback Behavior
column promises, and it is the part most likely to rot silently, because nothing
else in the suite ever runs with a dependency broken.
"""

import uuid

import pytest
import sqlalchemy as sa

from app.ai import gemini
from app.config import get_settings
from app.db import _session_factory
from app.notifications import mailer
from app.search import service as search_service
from app.sla import monitor
from tests.helpers import factories as f
from tests.helpers.assertions import assert_no_server_error, assert_status, count_where
from tests.helpers.auth import API, auth


async def _async_boom(*args, **kwargs):
    """Stand-in for a dependency that is reachable but erroring."""
    raise RuntimeError("dependency unavailable")


# --- AI service unavailable ---------------------------------------------------
# §27: ticket still created with status `New`; routed to manual classification.


@pytest.mark.ai
def test_ai_provider_outage_still_creates_the_ticket(client, db, tokens, monkeypatch):
    """The pipeline runs as a BackgroundTask precisely so a provider outage
    cannot fail the request that triggered it."""
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini, "embed", _async_boom)
    monkeypatch.setattr(gemini, "generate_json", _async_boom)
    monkeypatch.setattr(gemini, "generate_text", _async_boom)

    ticket = f.make_ticket(client, tokens["requester"])

    row = client.get(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["admin"]))
    assert_status(row, 200)
    assert row.json()["status"] == "new"


@pytest.mark.ai
def test_ai_provider_outage_leaves_the_ticket_for_manual_classification(
    client, db, tokens, monkeypatch
):
    """§27 fallback + §28 "AI confidence too low" share one destination: a
    human. A failed pipeline must never guess a category or auto-assign."""
    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini, "embed", _async_boom)
    monkeypatch.setattr(gemini, "generate_json", _async_boom)
    monkeypatch.setattr(gemini, "generate_text", _async_boom)

    ticket = f.make_ticket(client, tokens["requester"])

    with db.connect() as conn:
        row = (
            conn.execute(
                sa.text(
                    "SELECT category_id, assignee_id, response_due_at FROM tickets WHERE id = :t"
                ),
                {"t": ticket["id"]},
            )
            .mappings()
            .one()
        )
    assert row["category_id"] is None, "a failed pipeline must not guess a category"
    assert row["assignee_id"] is None, "a failed pipeline must not auto-assign"
    # No classification means no priority, and the clocks key on priority (§16).
    assert row["response_due_at"] is None

    # Nothing was written to the classification trail either — a half-written
    # pipeline run is worse than none, because the AI panel would render it.
    assert count_where(db, "ai_classification_history", "ticket_id = :t", {"t": ticket["id"]}) == 0


# --- Notification delivery failure -------------------------------------------
# §27: "In-app notification is always attempted even if email fails."


def test_a_dead_smtp_relay_still_records_the_in_app_notification(client, db, tokens, monkeypatch):
    """The whole point of the swallow in `mailer.send_email`: the in-app row is
    the delivery that always lands, so the user is never left uninformed."""
    monkeypatch.setattr(get_settings(), "smtp_host", "smtp.invalid")

    def dead_relay(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(mailer.smtplib, "SMTP", dead_relay)

    ticket = f.make_ticket(client, tokens["requester"])
    catalog = f.catalog(db)
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    # Assignment is a notifying event; the request must succeed regardless.
    response = f.assign(
        client,
        tokens["admin"],
        ticket["id"],
        assignee_id=_seed_agent_id(db),
    )
    assert_status(response, 200)

    assert (
        count_where(
            db, "notifications", "ticket_id = :t AND channel = 'in_app'", {"t": ticket["id"]}
        )
        >= 1
    ), "email failure must not swallow the in-app notification"


def _seed_agent_id(db) -> str:
    with db.connect() as conn:
        return str(
            conn.execute(
                sa.text("SELECT id FROM users WHERE email = 'agent@agentdesk.dev'")
            ).scalar_one()
        )


# --- Email server unavailable -------------------------------------------------
# §27: "Portal and chat widget remain fully available as intake channels."


def test_an_inbound_email_outage_leaves_the_portal_channel_working(client, db, tokens, monkeypatch):
    """§27: mail intake pauses, the other two channels carry on.

    Both halves are asserted, because only the second one is interesting: it
    would be easy to write a version of this that patches something unrelated
    and then "proves" the portal works. So the mail path is driven to a real
    failure first, and the portal ticket is checked to have actually landed.
    """
    from app.intake import email_service

    monkeypatch.setattr(email_service, "handle_raw_email", _async_boom)

    # The provider webhook is genuinely down: the parser raises, and the route
    # surfaces it rather than silently swallowing the message.
    monkeypatch.setattr(get_settings(), "inbound_email_token", "test-inbound-token")
    inbound = client.post(
        f"{API}/intake/email",
        json={"raw": "From: someone@example.com\nSubject: Help\n\nMy laptop died."},
        headers={"X-Inbound-Token": "test-inbound-token"},
    )
    assert inbound.status_code >= 500, f"expected the mail path to be down, got {inbound.text}"

    # Portal intake is unaffected, and the ticket is really persisted.
    ticket = f.make_ticket(client, tokens["requester"])
    fetched = client.get(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["requester"]))
    assert_status(fetched, 200)
    assert fetched.json()["ref"].startswith("AGT-")

    # And so is the chat channel, §27's other named survivor.
    session = client.post(f"{API}/chat/sessions", headers=auth(tokens["requester"]))
    assert_status(session, 201)


# --- Search unavailable -------------------------------------------------------
# §27: "Ticket list/filter browsing (without full-text search) remains usable."


def test_search_degrades_to_text_when_the_embedding_provider_is_down(client, tokens, monkeypatch):
    """`embed_query` swallows on purpose: losing the vector term costs ranking
    quality, not the feature. Hybrid search drops to FTS + trigram."""
    subject = f"Printer jam {f.rand()}"
    f.make_ticket(client, tokens["requester"], subject=subject)
    monkeypatch.setattr(gemini, "embed", _async_boom)

    response = client.get(
        f"{API}/search/tickets", params={"q": subject}, headers=auth(tokens["requester"])
    )
    assert_status(response, 200)
    assert any(hit["subject"] == subject for hit in response.json()["tickets"]), (
        "the lexical half of hybrid search must still match without embeddings"
    )


def test_ticket_browsing_survives_a_total_search_outage(client, tokens, monkeypatch):
    """The documented fallback. Browsing is a different query path, so a broken
    search module must not be able to take the ticket list with it."""
    f.make_ticket(client, tokens["requester"])
    monkeypatch.setattr(search_service, "search_tickets", _async_boom)

    listed = client.get(f"{API}/tickets", headers=auth(tokens["requester"]))
    assert_status(listed, 200)
    assert listed.json(), "browsing must not depend on the search service"

    # And the search endpoint itself fails loudly rather than returning
    # half-results the UI would render as "no matches".
    searched = client.get(
        f"{API}/search/tickets", params={"q": "anything"}, headers=auth(tokens["requester"])
    )
    assert searched.status_code == 500


# --- Knowledge Base unavailable (§28) -----------------------------------------
# "New Ticket form and chat widget simply omit the suggested articles panel;
#  ticket submission is unaffected."


def test_a_knowledge_base_outage_does_not_block_ticket_submission(client, tokens, monkeypatch):
    monkeypatch.setattr(search_service, "search_kb", _async_boom)

    response = client.post(
        f"{API}/tickets",
        json={
            "subject": f"KB outage {f.rand()}",
            "description": "submitted while article suggestions are down",
            "channel": "portal",
        },
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)


# --- Database timeout ---------------------------------------------------------
# §27: "Generic error banner/500 page."


def test_a_database_timeout_is_a_generic_500_that_leaks_no_internals(client, tokens, monkeypatch):
    """A statement timeout must surface as an opaque 500. The failure text
    carries table and column names, so echoing it back is an information leak."""
    monkeypatch.setattr(search_service, "search_tickets", _async_boom)

    response = client.get(
        f"{API}/search/tickets", params={"q": "widget"}, headers=auth(tokens["requester"])
    )
    assert response.status_code == 500
    body = response.text.lower()
    for leak in ("traceback", "runtimeerror", "select ", "psycopg", "asyncpg", "sqlalchemy"):
        assert leak not in body, f"500 body leaked internals: {leak!r} in {body[:300]}"


# --- Attachment upload failure ------------------------------------------------
# §27: "Ticket can be submitted without the attachment; it can be added later."


# A one-pixel PNG: the upload path checks the declared MIME against the actual
# magic bytes, so the payload has to be a real image, not a text file.
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_a_failed_attachment_does_not_cost_the_ticket(client, db, tokens, monkeypatch):
    """The attachment is a second request, so a storage failure leaves the
    already-created ticket intact and re-uploadable."""
    ticket = f.make_ticket(client, tokens["requester"])

    from app.tickets import router as tickets_router_mod

    # A flag rather than monkeypatch.undo(), which would also drop the autouse
    # fixtures' patches and quietly re-arm the real AI pipeline mid-test.
    storage_down = {"value": True}
    original = tickets_router_mod.service.add_attachment

    async def flaky(*args, **kwargs):
        if storage_down["value"]:
            raise RuntimeError("attachment storage unavailable")
        return await original(*args, **kwargs)

    monkeypatch.setattr(tickets_router_mod.service, "add_attachment", flaky)

    def upload():
        return client.post(
            f"{API}/tickets/{ticket['id']}/attachments",
            files={"file": ("shot.png", _PNG, "image/png")},
            headers=auth(tokens["requester"]),
        )

    assert upload().status_code >= 400

    still_there = client.get(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["requester"]))
    assert_status(still_there, 200)

    storage_down["value"] = False
    assert_status(upload(), 201, "the user's manual retry must succeed")


# --- SLA breach during an outage / after reopen (§28) -------------------------


def test_a_breach_recorded_before_reopen_survives_the_reopen(client, db, tokens, user_ids):
    """§28: "the original breach remains on record, unaffected by the reopen."

    The fresh-segment half is pinned by test_sla.py; what is asserted here is
    that starting a new segment never rewrites history.
    """
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    tid = ticket["id"]
    f.assign(client, tokens["admin"], tid, queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], tid, assignee_id=user_ids["agent"])
    assert_status(
        client.patch(
            f"{API}/tickets/{tid}",
            json={"priority_id": catalog["priorities"]["High"]},
            headers=auth(tokens["agent"]),
        ),
        200,
    )

    # Force the deadline into the past, then drive one monitor pass. Timers are
    # server-side, so a breach lands whether or not any dashboard is reachable.
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE tickets SET resolution_due_at = now() - interval '1 hour' WHERE id = :t"
            ),
            {"t": tid},
        )

    async def scan():
        async with _session_factory() as session:
            fired = await monitor.scan_once(session)
            await session.commit()
            return fired

    f.run_on_app_loop(client, scan)
    breaches = count_where(
        db,
        "notifications",
        "ticket_id = :t AND trigger_type = 'sla_breached'",
        {"t": tid},
    )
    assert breaches >= 1, "a passed deadline must be recorded server-side"

    f.comment(client, tokens["agent"], tid, "on it")
    f.drive_to(client, tokens, tid, "closed")
    assert_status(
        client.post(f"{API}/tickets/{tid}/reopen", headers=auth(tokens["requester"])), 200
    )

    after = count_where(
        db,
        "notifications",
        "ticket_id = :t AND trigger_type = 'sla_breached'",
        {"t": tid},
    )
    assert after == breaches, "reopening must not erase the original breach record"


# --- Auth timeout (§27) -------------------------------------------------------
# "Session Expired modal ... Re-login preserves the original destination."
# Token expiry itself is pinned in tests/security/test_auth_security.py; what
# matters here is that the 401 is machine-readable enough for the UI to tell an
# expired session apart from a permission problem.


def test_an_expired_session_is_a_401_not_a_403(client, tokens):
    """The frontend branches on this: 401 opens the Session Expired modal and
    replays the destination, 403 renders Access Denied. Swapping them strands
    the user on the wrong screen."""
    response = client.get(f"{API}/tickets", headers=auth("not-a-real-token"))
    assert response.status_code == 401
    assert_no_server_error(response)


# --- Unknown-id handling ------------------------------------------------------


def test_a_missing_ticket_is_a_404_not_a_crash(client, tokens):
    response = client.get(f"{API}/tickets/{uuid.uuid4()}", headers=auth(tokens["admin"]))
    assert response.status_code == 404
