"""Phase 8 checkpoint: hybrid search scoped per role, saved-view CRUD, live
dashboard metrics, and report generate/poll/export in all three formats.

Runs against the migrated + seeded database. AI is disabled in the suite, so
search degrades to FTS + trigram (no vector term) — the blend + scoping is what
this exercises.
"""

import uuid

import pytest

SEED_PASSWORD = "Password123!"
SEED_USERS = {
    "requester": "requester@agentdesk.dev",
    "agent": "agent@agentdesk.dev",
    "team_lead": "lead@agentdesk.dev",
    "admin": "admin@agentdesk.dev",
}
API = "/api/v1"


@pytest.fixture(scope="module")
def tokens(client) -> dict[str, str]:
    out = {}
    for role, email in SEED_USERS.items():
        r = client.post(f"{API}/auth/login", json={"email": email, "password": SEED_PASSWORD})
        out[role] = r.json()["access_token"]
    return out


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create(client, token, subject) -> dict:
    r = client.post(
        f"{API}/tickets",
        json={"subject": subject, "description": "body text"},
        headers=_auth(token),
    )
    assert r.status_code == 201, r.text
    return r.json()


# --- Search ---


def test_search_blends_and_scopes_by_role(client, tokens):
    token = f"unicorn{uuid.uuid4().hex[:8]}"  # a lexeme that exists nowhere else
    _create(client, tokens["requester"], f"{token} keyboard issue")
    admin_only = f"adminsecret{uuid.uuid4().hex[:8]}"
    _create(client, tokens["admin"], f"{admin_only} internal thing")

    # Requester finds their own ticket
    r = client.get(f"{API}/search/tickets", params={"q": token}, headers=_auth(tokens["requester"]))
    assert r.status_code == 200, r.text
    subjects = [t["subject"] for t in r.json()["tickets"]]
    assert any(token in s for s in subjects)

    # Requester does NOT see the admin-owned ticket (scope_tickets_to_caller)
    r = client.get(
        f"{API}/search/tickets", params={"q": admin_only}, headers=_auth(tokens["requester"])
    )
    assert r.json()["tickets"] == []

    # Admin sees it org-wide
    r = client.get(
        f"{API}/search/tickets", params={"q": admin_only}, headers=_auth(tokens["admin"])
    )
    assert any(admin_only in t["subject"] for t in r.json()["tickets"])


def test_search_metadata_filter(client, tokens):
    token = f"filtertok{uuid.uuid4().hex[:8]}"
    _create(client, tokens["requester"], f"{token} thing")
    r = client.get(
        f"{API}/search/tickets",
        params={"q": token, "status": "new"},
        headers=_auth(tokens["requester"]),
    )
    assert all(t["status"] == "new" for t in r.json()["tickets"])
    r = client.get(
        f"{API}/search/tickets",
        params={"q": token, "status": "closed"},
        headers=_auth(tokens["requester"]),
    )
    assert r.json()["tickets"] == []


# --- Saved views ---


def test_saved_views_crud_and_ownership(client, tokens):
    r = client.post(
        f"{API}/saved-views",
        json={"name": "My open", "filters": {"status": "open"}},
        headers=_auth(tokens["agent"]),
    )
    assert r.status_code == 201, r.text
    view_id = r.json()["id"]

    assert any(
        v["id"] == view_id
        for v in client.get(f"{API}/saved-views", headers=_auth(tokens["agent"])).json()
    )

    r = client.patch(
        f"{API}/saved-views/{view_id}", json={"name": "Renamed"}, headers=_auth(tokens["agent"])
    )
    assert r.json()["name"] == "Renamed"

    # Another user cannot touch it (ownership enforced on patch/delete)
    assert (
        client.patch(
            f"{API}/saved-views/{view_id}", json={"name": "x"}, headers=_auth(tokens["admin"])
        ).status_code
        == 404
    )

    assert (
        client.delete(f"{API}/saved-views/{view_id}", headers=_auth(tokens["agent"])).status_code
        == 204
    )
    assert (
        client.delete(f"{API}/saved-views/{view_id}", headers=_auth(tokens["agent"])).status_code
        == 404
    )


# --- Dashboard ---


def test_dashboard_metrics_shape_and_rbac(client, tokens):
    r = client.get(f"{API}/dashboard/metrics", headers=_auth(tokens["admin"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "open_ticket_count",
        "avg_resolution_seconds",
        "sla_compliance_rate",
        "agent_workload",
    }
    assert isinstance(body["open_ticket_count"], int)

    # Requesters have no dashboard
    assert (
        client.get(f"{API}/dashboard/metrics", headers=_auth(tokens["requester"])).status_code
        == 403
    )


# --- Reports ---


@pytest.mark.parametrize("report_type", ["ai_performance", "sla_compliance", "ticket_trends"])
def test_report_generate_poll_export(client, tokens, report_type):
    r = client.post(
        f"{API}/reports/generate",
        json={"report_type": report_type},
        headers=_auth(tokens["admin"]),
    )
    assert r.status_code == 202, r.text
    report_id = r.json()["id"]

    # TestClient runs the background task before returning, so it is ready now
    r = client.get(f"{API}/reports/{report_id}", headers=_auth(tokens["admin"]))
    assert r.json()["status"] == "ready", r.json()

    for fmt, magic in (("csv", None), ("xlsx", b"PK"), ("pdf", b"%PDF")):
        r = client.get(
            f"{API}/reports/{report_id}/export",
            params={"format": fmt},
            headers=_auth(tokens["admin"]),
        )
        assert r.status_code == 200, r.text
        assert "attachment" in r.headers["content-disposition"]
        if magic:
            assert r.content[: len(magic)] == magic


def test_report_unknown_type_and_ownership(client, tokens):
    assert (
        client.post(
            f"{API}/reports/generate", json={"report_type": "nope"}, headers=_auth(tokens["admin"])
        ).status_code
        == 422
    )
    r = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=_auth(tokens["admin"]),
    )
    report_id = r.json()["id"]
    # A different user cannot read someone else's report
    assert (
        client.get(f"{API}/reports/{report_id}", headers=_auth(tokens["agent"])).status_code == 404
    )
