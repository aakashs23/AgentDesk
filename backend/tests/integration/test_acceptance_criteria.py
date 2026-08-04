"""Document 01, Acceptance Criteria — one test per line of the list.

The rest of the suite is organised by module, which is the right shape for
finding a regression but the wrong shape for answering "is the product done?".
This file is the traceability layer: six criteria, six named tests, each one
end-to-end through the API the way the criterion is written. Depth stays where
it already lives (`test_sla.py`, `test_permissions.py`, `test_ai.py`); what these
add is a single place that fails if a *criterion* stops being met.

The one criterion with no automatable form is called out at
`test_ai_classification_accuracy_is_measured_against_human_corrections`.
"""

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_forbidden, assert_status
from tests.helpers.auth import API, auth

# --- AC 1: "Ticket is created successfully with all required fields and a
#            confirmation is returned to the requester" ------------------------


def test_a_created_ticket_returns_a_confirmation_to_the_requester(client, db, tokens):
    subject = f"Laptop will not boot {f.rand()}"
    response = client.post(
        f"{API}/tickets",
        json={"subject": subject, "description": "It powers off at the logo.", "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)
    body = response.json()

    # The confirmation is the reference the requester quotes back at us; it is
    # also what email threading matches on (App Flow §11), so it must be present
    # in the create response and not only on a later read.
    assert body["ref"].startswith("AGT-"), body
    assert body["status"] == "new"
    assert body["subject"] == subject
    assert body["created_at"]

    # "created successfully" means persisted, not just echoed.
    fetched = client.get(f"{API}/tickets/{body['id']}", headers=auth(tokens["requester"]))
    assert_status(fetched, 200)
    assert fetched.json()["ref"] == body["ref"]


def test_a_ticket_missing_a_required_field_is_rejected(client, tokens):
    """The other half of "with all required fields"."""
    for payload in ({"description": "no subject"}, {"subject": "no description"}, {}):
        response = client.post(f"{API}/tickets", json=payload, headers=auth(tokens["requester"]))
        assert response.status_code == 422, payload


# --- AC 2: "AI classification accuracy exceeds 85% agreement with human-assigned
#            category" --------------------------------------------------------


def test_ai_classification_accuracy_is_measured_against_human_corrections(client, db, tokens):
    """The *metric* is what this pins, not the 85% threshold.

    `classification_accuracy` is `1 - corrected/total` over
    `ai_classification_history` — literally "agreement with the human-assigned
    category". A test can guarantee that number is computed honestly; it cannot
    guarantee the model clears 85%, because that is a property of a trained
    DistilBERT checkpoint and a labelled evaluation set, neither of which lives
    in this repo (the checkpoint is gitignored, per CLAUDE.md).

    Documented exception, carried into Phase 16 with the other open model
    decisions: the 85% gate is verified by running the AI Performance report
    against real graded data, not by this suite.
    """
    ticket = f.make_ticket(client, tokens["requester"])
    with db.begin() as conn:
        priority_id = conn.execute(sa.text("SELECT id FROM priorities LIMIT 1")).scalar_one()
        category_id = conn.execute(sa.text("SELECT id FROM categories LIMIT 1")).scalar_one()
        # Two classifications on this ticket: one the human accepted, one they
        # corrected. Agreement over just these two rows is 50%.
        #
        # Backdated 30 days on purpose. `ai_performance` has no default date
        # window so these still count towards accuracy, but the *trend* report
        # buckets by day, and `test_the_ai_trend_report_never_double_counts_a_day`
        # asserts `classifications <= drafts` on today's bucket. Classifications
        # with no matching draft are legitimate (App Flow §14: the low-confidence
        # branch ends before the draft node), so writing them into today's bucket
        # breaks a neighbouring test's arithmetic rather than finding a bug.
        for corrected in (None, category_id):
            conn.execute(
                sa.text(
                    "INSERT INTO ai_classification_history (ticket_id, predicted_priority_id, "
                    "corrected_category_id, confidence, confidence_tier, model_version, "
                    "created_at) "
                    "VALUES (:t, :p, :c, 90, 'high', 'ac-test', now() - interval '30 days')"
                ),
                {"t": ticket["id"], "p": priority_id, "c": corrected},
            )

    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ai_performance"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 202)
    rows = client.get(
        f"{API}/reports/{created.json()['id']}", headers=auth(tokens["admin"])
    ).json()["rows"]
    by_metric = {r["metric"]: r["value"] for r in rows}

    accuracy = by_metric["classification_accuracy"]
    assert accuracy is not None, "accuracy must be reported once any classification exists"
    assert 0.0 <= accuracy < 1.0, (
        f"a corrected classification must pull accuracy below 1.0, got {accuracy}"
    )
    assert by_metric["classifications_total"] >= 2


# --- AC 3: "Auto-routing correctly assigns tickets per configured rules" ------


@pytest.mark.ai
def test_auto_routing_assigns_a_high_confidence_ticket(client, db, tokens, monkeypatch):
    """App Flow §14: only the high-confidence branch auto-routes. The medium and
    low branches are pinned in `test_ai.py`; this is the criterion's happy path."""
    from app.ai import classifier, gemini, pipeline  # noqa: F401
    from app.config import get_settings
    from app.models import EMBEDDING_DIM

    monkeypatch.setattr(get_settings(), "gemini_api_key", "test-key")

    async def fake_embed(text: str) -> list[float]:
        return [1.0] + [0.0] * (EMBEDDING_DIM - 1)

    async def fake_generate_json(prompt: str, schema: dict) -> dict:
        return {"category": "Refunds", "priority": "High", "confidence": 95}

    async def fake_generate_text(prompt: str) -> str:
        return "Draft reply."

    monkeypatch.setattr(gemini, "embed", fake_embed)
    monkeypatch.setattr(gemini, "generate_json", fake_generate_json)
    monkeypatch.setattr(gemini, "generate_text", fake_generate_text)
    monkeypatch.setattr(classifier, "predict", lambda text: ("Refunds", 0.9))

    ticket = f.make_ticket(
        client, tokens["requester"], subject=f"Refund request {f.rand()}", description="refund me"
    )

    insights = client.get(f"{API}/tickets/{ticket['id']}/ai", headers=auth(tokens["admin"]))
    assert_status(insights, 200)
    assert insights.json()["classification"]["confidence_tier"] == "high"

    with db.connect() as conn:
        row = (
            conn.execute(
                sa.text("SELECT category_id, queue_id FROM tickets WHERE id = :t"),
                {"t": ticket["id"]},
            )
            .mappings()
            .one()
        )
    assert row["category_id"] is not None, "a high-confidence ticket must be categorised"
    assert row["queue_id"] is not None, "a high-confidence ticket must land in a queue"


# --- AC 4: "SLA alerts trigger at the correct threshold" ----------------------


def test_sla_alerts_fire_at_warning_and_at_breach(client, db, tokens, user_ids):
    """Two thresholds, two distinct trigger types, and neither fires early."""
    from app.db import _session_factory
    from app.sla import monitor

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

    async def scan():
        async with _session_factory() as session:
            fired = await monitor.scan_once(session)
            await session.commit()
            return fired

    def alerts(trigger: str) -> int:
        """Distinct recipients, not rows: `notify` fans one event out to every
        channel the recipient enabled, so a row count would count deliveries."""
        with db.connect() as conn:
            return conn.execute(
                sa.text(
                    "SELECT count(DISTINCT user_id) FROM notifications "
                    "WHERE ticket_id = :t AND trigger_type = :g"
                ),
                {"t": tid, "g": trigger},
            ).scalar_one()

    # A deadline comfortably in the future must not alert at all.
    f.run_on_app_loop(client, scan)
    assert alerts("sla_warning") == 0, "warned before the threshold"
    assert alerts("sla_breached") == 0, "breached before the deadline"

    # Inside the warning window but not yet past the deadline → warning only.
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE tickets SET resolution_due_at = now() + interval '2 minutes' WHERE id = :t"
            ),
            {"t": tid},
        )
    f.run_on_app_loop(client, scan)
    assert alerts("sla_warning") == 1, "no warning as the deadline approached"
    assert alerts("sla_breached") == 0, "breached while still inside the deadline"

    # Past the deadline → breach.
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE tickets SET resolution_due_at = now() - interval '1 minute' WHERE id = :t"
            ),
            {"t": tid},
        )
    f.run_on_app_loop(client, scan)
    assert alerts("sla_breached") == 1, "no breach after the deadline passed"


# --- AC 5: "Role-based access control is enforced (e.g. an Agent cannot access
#            Admin configuration settings)" ------------------------------------


ADMIN_CONFIG_SURFACES = [
    ("POST", "/admin/teams", {"name": "x"}),
    ("POST", "/admin/queues", {"name": "x"}),
    ("POST", "/admin/sla-rules", {}),
    ("POST", "/admin/categories", {"name": "x"}),
    ("POST", "/admin/priorities", {"name": "x", "rank": 9, "color_hex": "#000000"}),
    ("GET", "/admin/audit-logs", None),
]


@pytest.mark.parametrize("method,path,body", ADMIN_CONFIG_SURFACES)
def test_an_agent_cannot_reach_admin_configuration(client, tokens, method, path, body):
    """The criterion names the Agent explicitly. Direct-URL access is the whole
    point — there is no client-side route guard to rely on."""
    request = client.request(method, f"{API}{path}", json=body, headers=auth(tokens["agent"]))
    assert_forbidden(request, f"{method} {path}")


@pytest.mark.parametrize("method,path,body", ADMIN_CONFIG_SURFACES)
def test_a_requester_cannot_reach_admin_configuration(client, tokens, method, path, body):
    request = client.request(method, f"{API}{path}", json=body, headers=auth(tokens["requester"]))
    assert_forbidden(request, f"{method} {path}")


def test_a_requester_cannot_read_another_requesters_ticket(client, db, tokens):
    """RBAC is row scope as well as route access — the half a route guard misses."""
    other = f.verified_requester(client, db)
    theirs = f.make_ticket(client, other["token"])
    # 404, not 403: an out-of-scope row must not confirm its own existence.
    response = client.get(f"{API}/tickets/{theirs['id']}", headers=auth(tokens["requester"]))
    assert response.status_code == 404, response.text


# --- AC 6: "Reports export correctly in CSV/PDF/Excel formats" ----------------


@pytest.mark.parametrize(
    "fmt,content_type,magic",
    [
        ("csv", "text/csv", b""),
        (
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            b"PK\x03\x04",
        ),
        ("pdf", "application/pdf", b"%PDF"),
    ],
)
def test_a_report_exports_in_each_required_format(client, tokens, fmt, content_type, magic):
    """ "Correctly" means the bytes are actually that format — a CSV renamed
    `.pdf` would pass a status-code-only check."""
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 202)
    report_id = created.json()["id"]
    assert (
        client.get(f"{API}/reports/{report_id}", headers=auth(tokens["admin"])).json()["status"]
        == "ready"
    )

    export = client.get(
        f"{API}/reports/{report_id}/export",
        params={"format": fmt},
        headers=auth(tokens["admin"]),
    )
    assert_status(export, 200, f"export as {fmt}")
    assert content_type in export.headers["content-type"]
    assert export.content, f"{fmt} export was empty"
    if magic:
        assert export.content.startswith(magic), f"{fmt} export is not really a {fmt}"
    else:
        # CSV: a header row of comma-separated names, decodable as text.
        first_line = export.content.decode().splitlines()[0]
        assert "," in first_line, f"CSV export has no header row: {first_line!r}"
