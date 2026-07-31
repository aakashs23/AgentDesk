"""Dashboard metrics and generated reports (Phase 8; TRD §12).

Metrics are asserted as *deltas* wherever possible. The suite shares one
database and other tests create tickets constantly, so any test that pinned an
absolute count would be measuring the rest of the suite rather than the code.
"""

from datetime import UTC, datetime

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth

REPORT_TYPES = [
    "agent_productivity",
    "sla_compliance",
    "ticket_trends",
    "ai_performance",
    "category_analytics",
    "ai_performance_trend",
]


def _metrics(client, token) -> dict:
    response = client.get(f"{API}/dashboard/metrics", headers=auth(token))
    assert_status(response, 200)
    return response.json()


# --- Dashboard ---


def test_dashboard_has_the_documented_shape(client, tokens):
    body = _metrics(client, tokens["admin"])
    assert set(body) == {
        "open_ticket_count",
        "avg_resolution_seconds",
        "sla_compliance_rate",
        "agent_workload",
    }, sorted(body)
    assert isinstance(body["open_ticket_count"], int)
    assert isinstance(body["agent_workload"], list)
    for row in body["agent_workload"]:
        assert set(row) == {"assignee_id", "full_name", "open_tickets"}


def test_a_new_ticket_increments_the_open_count(client, tokens):
    before = _metrics(client, tokens["admin"])["open_ticket_count"]
    f.make_ticket(client, tokens["requester"])
    after = _metrics(client, tokens["admin"])["open_ticket_count"]
    assert after == before + 1, f"open count went from {before} to {after}"


def test_resolving_a_ticket_removes_it_from_the_open_count(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    before = _metrics(client, tokens["admin"])["open_ticket_count"]

    f.drive_to(client, tokens, ticket["id"], "resolved")
    after = _metrics(client, tokens["admin"])["open_ticket_count"]
    assert after == before - 1, f"open count went from {before} to {after} after resolving"


def test_agent_workload_reflects_a_new_assignment(client, db, tokens, user_ids):
    catalog = f.catalog(db)

    def workload_for(user_id):
        rows = _metrics(client, tokens["admin"])["agent_workload"]
        return next((r["open_tickets"] for r in rows if r["assignee_id"] == user_id), 0)

    before = workload_for(user_ids["agent"])
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])

    assert workload_for(user_ids["agent"]) == before + 1


def test_metrics_are_scoped_to_the_caller(client, db, tokens):
    """An agent on a fresh team sees only their own slice, never the org total."""
    catalog = f.catalog(db)
    admin_total = _metrics(client, tokens["admin"])["open_ticket_count"]

    agent = f.activated_user(client, db, tokens["admin"], "agent", team_id=catalog["team_id"])
    agent_total = _metrics(client, agent["token"])["open_ticket_count"]
    assert agent_total <= admin_total, "an agent saw more tickets than the admin"


def test_sla_compliance_is_a_rate_or_null(client, tokens):
    rate = _metrics(client, tokens["admin"])["sla_compliance_rate"]
    assert rate is None or 0.0 <= rate <= 1.0, rate


def test_a_resolved_ticket_contributes_to_average_resolution_time(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.drive_to(client, tokens, ticket["id"], "resolved")

    average = _metrics(client, tokens["admin"])["avg_resolution_seconds"]
    assert average is not None, "no average after resolving a ticket"
    assert average >= 0


# --- Reports ---


@pytest.mark.parametrize("report_type", REPORT_TYPES)
def test_every_report_type_generates_and_is_readable(client, tokens, report_type):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": report_type},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 202, report_type)
    report_id = created.json()["id"]

    fetched = client.get(f"{API}/reports/{report_id}", headers=auth(tokens["admin"]))
    assert_status(fetched, 200)
    body = fetched.json()
    assert body["status"] == "ready", f"{report_type} is {body['status']}: {body['error']}"
    assert body["columns"], f"{report_type} produced no columns"
    assert isinstance(body["rows"], list)
    for row in body["rows"]:
        assert set(row) <= set(body["columns"]), f"row keys outside declared columns: {row}"


@pytest.mark.parametrize("fmt", ["csv", "xlsx", "pdf"])
def test_a_ready_report_exports_in_every_format(client, tokens, fmt):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["admin"]),
    )
    report_id = created.json()["id"]

    exported = client.get(
        f"{API}/reports/{report_id}/export", params={"format": fmt}, headers=auth(tokens["admin"])
    )
    assert_status(exported, 200, fmt)
    assert exported.content, f"{fmt} export was empty"
    assert exported.headers["content-disposition"].startswith("attachment")

    signatures = {"xlsx": b"PK\x03\x04", "pdf": b"%PDF"}
    if fmt in signatures:
        assert exported.content.startswith(signatures[fmt]), f"{fmt} content is not a real {fmt}"
    else:
        assert b"day" in exported.content, "the CSV has no header row"


def test_report_rows_are_paginated(client, tokens):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["admin"]),
    )
    report_id = created.json()["id"]

    full = client.get(f"{API}/reports/{report_id}", headers=auth(tokens["admin"])).json()
    page = client.get(
        f"{API}/reports/{report_id}",
        params={"limit": 1, "offset": 0},
        headers=auth(tokens["admin"]),
    ).json()
    assert len(page["rows"]) <= 1
    if full["rows"]:
        assert page["rows"] == full["rows"][:1]


def test_a_date_range_filters_the_report(client, tokens):
    """A window entirely in the past must return fewer rows than an open one."""
    unbounded = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["admin"]),
    ).json()["id"]
    bounded = client.post(
        f"{API}/reports/generate",
        json={
            "report_type": "ticket_trends",
            "start_date": "2000-01-01T00:00:00Z",
            "end_date": "2000-01-02T00:00:00Z",
        },
        headers=auth(tokens["admin"]),
    ).json()["id"]

    all_rows = client.get(f"{API}/reports/{unbounded}", headers=auth(tokens["admin"])).json()[
        "rows"
    ]
    windowed = client.get(f"{API}/reports/{bounded}", headers=auth(tokens["admin"])).json()["rows"]
    assert windowed == [], "a report window in the year 2000 returned rows"
    assert all_rows, "the unbounded report returned nothing to compare against"


def test_exporting_a_report_that_is_not_ready_is_refused(client, tokens, monkeypatch):
    from app.reporting import service as reporting

    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["admin"]),
    )
    report_id = created.json()["id"]
    reporting.get_report(__import__("uuid").UUID(report_id)).status = "pending"

    response = client.get(
        f"{API}/reports/{report_id}/export", params={"format": "csv"}, headers=auth(tokens["admin"])
    )
    assert_status(response, 409, "exported a report that was not ready")


def test_report_generation_is_scoped_to_the_caller(client, db, tokens):
    """A report must not become a way around ticket-level scoping."""
    catalog = f.catalog(db)
    agent = f.activated_user(client, db, tokens["admin"], "agent", team_id=catalog["team_id"])

    for token, key in ((tokens["admin"], "admin"), (agent["token"], "agent")):
        created = client.post(
            f"{API}/reports/generate",
            json={"report_type": "category_analytics"},
            headers=auth(token),
        )
        assert_status(created, 202, key)
        rows = client.get(
            f"{API}/reports/{created.json()['id']}", params={"limit": 1000}, headers=auth(token)
        ).json()["rows"]
        total = sum(r["count"] for r in rows)
        if key == "admin":
            admin_total = total
        else:
            assert total <= admin_total, "an agent's report covered more than the admin's"


def test_ai_performance_rates_are_bounded(client, tokens):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ai_performance"},
        headers=auth(tokens["admin"]),
    )
    rows = client.get(
        f"{API}/reports/{created.json()['id']}", headers=auth(tokens["admin"])
    ).json()["rows"]
    by_metric = {r["metric"]: r["value"] for r in rows}
    for metric in (
        "classification_accuracy",
        "auto_routing_acceptance_rate",
        "draft_approval_rate",
    ):
        value = by_metric[metric]
        assert value is None or 0.0 <= value <= 1.0, f"{metric} = {value}"
    assert by_metric["drafts_total"] >= 0


def test_the_ai_trend_report_never_double_counts_a_day(client, db, tokens):
    """Classifications and drafts are counted separately and joined by day: one
    ticket can carry several drafts against a single classification, so a SQL
    join between the two tables would inflate the classification count."""
    import sqlalchemy as sa

    ticket = f.make_ticket(client, tokens["requester"])
    with db.begin() as conn:
        catalog = conn.execute(sa.text("SELECT id FROM priorities LIMIT 1")).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO ai_classification_history "
                "(ticket_id, predicted_priority_id, confidence, confidence_tier, model_version) "
                "VALUES (:t, :p, 90, 'high', 'test')"
            ),
            {"t": ticket["id"], "p": catalog},
        )
        for status in ("approved", "edited", "rejected"):
            conn.execute(
                sa.text(
                    "INSERT INTO ai_draft_history "
                    "(ticket_id, generated_by_model, draft_content, review_status) "
                    "VALUES (:t, 'test', 'draft', :s)"
                ),
                {"t": ticket["id"], "s": status},
            )

    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ai_performance_trend"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 202)
    report = client.get(
        f"{API}/reports/{created.json()['id']}", headers=auth(tokens["admin"])
    ).json()
    assert report["status"] == "ready", report["error"]

    today = datetime.now(UTC).date().isoformat()
    row = next(r for r in report["rows"] if r["day"].startswith(today))
    # Three drafts against one classification: the classification is counted once.
    assert row["drafts"] >= 3
    assert row["classifications"] >= 1
    assert row["classifications"] <= row["drafts"], "classifications inflated by the draft join"
    # Two of the three drafts (approved + edited) count as accepted.
    assert 0 < row["draft_approval_rate"] < 1
