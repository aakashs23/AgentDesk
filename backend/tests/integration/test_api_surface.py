"""What the API actually exposes, and what it does not.

Two jobs. First, pin the routing table so an accidental removal or a changed
prefix fails loudly. Second — and the reason this file exists — record the
endpoints the verification brief expected to find but which are **not
implemented**, so "missing" is a tracked, executable fact rather than a note in
a document nobody re-reads.

The absent-endpoint tests assert 404. They pass today *because* the feature is
missing. When one is built, its test fails and points here, which is the signal
to move it into a real integration suite.
"""

import pytest

from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth

# Every route the app mounts, as (method, path template).
EXPECTED_ROUTES = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("POST", "/api/v1/auth/verify-email"),
    ("POST", "/api/v1/auth/password-change"),
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/users"),
    ("GET", "/api/v1/users/{user_id}"),
    ("PATCH", "/api/v1/users/{user_id}"),
    ("DELETE", "/api/v1/users/{user_id}"),
    ("GET", "/api/v1/tickets"),
    ("POST", "/api/v1/tickets"),
    ("GET", "/api/v1/tickets/{ticket_id}"),
    ("PATCH", "/api/v1/tickets/{ticket_id}"),
    ("PATCH", "/api/v1/tickets/{ticket_id}/status"),
    ("GET", "/api/v1/tickets/{ticket_id}/status-history"),
    ("POST", "/api/v1/tickets/{ticket_id}/reopen"),
    ("POST", "/api/v1/tickets/{ticket_id}/assign"),
    ("POST", "/api/v1/tickets/{ticket_id}/escalate"),
    ("POST", "/api/v1/tickets/{ticket_id}/merge"),
    ("POST", "/api/v1/tickets/{ticket_id}/split"),
    ("GET", "/api/v1/tickets/{ticket_id}/comments"),
    ("POST", "/api/v1/tickets/{ticket_id}/comments"),
    ("PATCH", "/api/v1/comments/{comment_id}"),
    ("DELETE", "/api/v1/comments/{comment_id}"),
    ("POST", "/api/v1/tickets/{ticket_id}/attachments"),
    ("GET", "/api/v1/tickets/{ticket_id}/attachments"),
    ("GET", "/api/v1/attachments/{attachment_id}"),
    ("DELETE", "/api/v1/attachments/{attachment_id}"),
    ("GET", "/api/v1/tags"),
    ("POST", "/api/v1/tags"),
    ("POST", "/api/v1/tickets/{ticket_id}/tags"),
    # Phase 10 — the Customer Portal's read surface plus CSAT
    ("GET", "/api/v1/categories"),
    ("GET", "/api/v1/priorities"),
    ("GET", "/api/v1/knowledge-base/articles"),
    ("GET", "/api/v1/knowledge-base/articles/{article_id}"),
    # Phase 11 — the Agent Console's KB creation loop (App Flow §19)
    ("POST", "/api/v1/knowledge-base/articles"),
    ("PATCH", "/api/v1/knowledge-base/articles/{article_id}"),
    # Phase 12 — Admin Dashboard configuration CRUD (TRD §3)
    ("DELETE", "/api/v1/knowledge-base/articles/{article_id}"),
    ("GET", "/api/v1/admin/teams"),
    ("POST", "/api/v1/admin/teams"),
    ("PATCH", "/api/v1/admin/teams/{team_id}"),
    ("DELETE", "/api/v1/admin/teams/{team_id}"),
    ("GET", "/api/v1/admin/queues"),
    ("POST", "/api/v1/admin/queues"),
    ("PATCH", "/api/v1/admin/queues/{queue_id}"),
    ("DELETE", "/api/v1/admin/queues/{queue_id}"),
    ("POST", "/api/v1/admin/categories"),
    ("PATCH", "/api/v1/admin/categories/{category_id}"),
    ("DELETE", "/api/v1/admin/categories/{category_id}"),
    ("POST", "/api/v1/admin/priorities"),
    ("PATCH", "/api/v1/admin/priorities/{priority_id}"),
    ("DELETE", "/api/v1/admin/priorities/{priority_id}"),
    ("GET", "/api/v1/admin/sla-rules"),
    ("POST", "/api/v1/admin/sla-rules"),
    ("PATCH", "/api/v1/admin/sla-rules/{rule_id}"),
    ("DELETE", "/api/v1/admin/sla-rules/{rule_id}"),
    ("GET", "/api/v1/admin/audit-logs"),
    ("GET", "/api/v1/admin/audit-logs/entity-types"),
    ("GET", "/api/v1/csat"),
    ("POST", "/api/v1/csat"),
    ("GET", "/api/v1/tickets/{ticket_id}/ai"),
    ("POST", "/api/v1/ai/drafts/{draft_id}/review"),
    ("POST", "/api/v1/tickets/{ticket_id}/classification/confirm"),
    ("POST", "/api/v1/tickets/{ticket_id}/classification/correct"),
    ("GET", "/api/v1/admin/automation-rules"),
    ("POST", "/api/v1/admin/automation-rules"),
    ("PATCH", "/api/v1/admin/automation-rules/{rule_id}"),
    ("DELETE", "/api/v1/admin/automation-rules/{rule_id}"),
    ("POST", "/api/v1/admin/automation-rules/preview"),
    ("GET", "/api/v1/admin/automation-logs"),
    ("GET", "/api/v1/notifications"),
    ("PATCH", "/api/v1/notifications/preferences"),
    ("PATCH", "/api/v1/notifications/{notification_id}/read"),
    ("GET", "/api/v1/notification-templates"),
    ("POST", "/api/v1/notification-templates"),
    ("PATCH", "/api/v1/notification-templates/{template_id}"),
    ("DELETE", "/api/v1/notification-templates/{template_id}"),
    ("GET", "/api/v1/webhooks"),
    ("POST", "/api/v1/webhooks"),
    ("PATCH", "/api/v1/webhooks/{webhook_id}"),
    ("DELETE", "/api/v1/webhooks/{webhook_id}"),
    ("GET", "/api/v1/webhooks/{webhook_id}/deliveries"),
    ("GET", "/api/v1/search/tickets"),
    ("GET", "/api/v1/saved-views"),
    ("POST", "/api/v1/saved-views"),
    ("PATCH", "/api/v1/saved-views/{view_id}"),
    ("DELETE", "/api/v1/saved-views/{view_id}"),
    ("GET", "/api/v1/dashboard/metrics"),
    ("POST", "/api/v1/reports/generate"),
    ("GET", "/api/v1/reports/{report_id}"),
    ("GET", "/api/v1/reports/{report_id}/export"),
    ("GET", "/health"),
    ("GET", "/health/ready"),
}


def _actual_routes(client) -> set[tuple[str, str]]:
    """Read the surface from the OpenAPI schema rather than `app.routes`.

    FastAPI keeps included routers nested rather than flattened onto the parent,
    so walking `app.routes` only sees the routes declared on `main` itself. The
    generated schema is the flattened, authoritative view.
    """
    schema = client.get("/openapi.json").json()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method.upper() not in {"HEAD", "OPTIONS"}
    }


def test_the_route_table_is_exactly_what_is_documented_here(client):
    """Fails on both directions of drift: a removed route and an unlisted new
    one. Update this set deliberately when the surface changes."""
    actual = _actual_routes(client)
    assert actual == EXPECTED_ROUTES, (
        f"routes added: {sorted(actual - EXPECTED_ROUTES)}\n"
        f"routes removed: {sorted(EXPECTED_ROUTES - actual)}"
    )


def test_every_feature_route_is_under_the_versioned_prefix(client):
    """TRD §3: only the health probes live outside /api/v1."""
    unversioned = {
        path
        for _method, path in _actual_routes(client)
        if not path.startswith(("/api/v1", "/health"))
    }
    assert not unversioned, f"unversioned routes: {sorted(unversioned)}"


# --- Endpoints the verification brief expected but which do not exist ---

# Phase 10 filled several of these in for the Customer Portal — the read side of
# categories/priorities/knowledge base, all of CSAT, and authenticated password
# change. They are covered properly in test_portal_api.py now. Phase 11 added the
# knowledge-base write half for App Flow §19's creation loop (test_agent_api.py).
# Phase 12 added the whole admin configuration surface — teams, queues, category
# and priority writes, SLA rules and the audit-log reader — under TRD §3's
# `/admin/...` prefix rather than the bare paths guessed at here; see
# test_admin_config.py. What is left is genuinely unbuilt.
MISSING_ENDPOINTS = {
    # No settings/branding table exists in Doc 05 and the schema invariant
    # forbids adding one, so `PATCH /admin/config` (TRD §3) stays unbuilt: the
    # Admin's Templates & Branding screen edits notification templates only.
    "application settings": [("GET", "/settings"), ("PATCH", "/settings")],
    "bulk ticket operations": [("POST", "/tickets/bulk")],
    "ticket deletion": [("DELETE", "/tickets")],
    "OCR on attachments": [("POST", "/attachments/ocr")],
}


@pytest.mark.parametrize(
    "feature,method,path",
    [(feature, m, p) for feature, routes in MISSING_ENDPOINTS.items() for m, p in routes],
    ids=[f"{feature}:{m} {p}" for feature, routes in MISSING_ENDPOINTS.items() for m, p in routes],
)
def test_unimplemented_feature_is_still_absent(client, tokens, feature, method, path):
    """Documents a gap. Passing means the feature is still missing; when it is
    built this fails, which is the prompt to write real tests for it."""
    response = client.request(method, f"{API}{path}", json={}, headers=auth(tokens["admin"]))
    assert response.status_code in (404, 405), (
        f"{feature} appears to be implemented now ({method} {path} → "
        f"{response.status_code}); move it out of MISSING_ENDPOINTS and test it properly"
    )


# `csat_responses` used to be listed here as schema-without-a-feature. Phase 10
# gave it an API for the Customer Portal's survey modal; see test_portal_api.py.


def test_the_conversation_history_table_exists_but_has_no_api(db):
    """Same for `conversation_history`: created by migration 0001, unused by the
    AI pipeline, which persists to ai_classification_history / ai_draft_history."""
    import sqlalchemy as sa

    with db.connect() as conn:
        assert conn.execute(sa.text("SELECT to_regclass('public.conversation_history')")).scalar()
        rows = conn.execute(sa.text("SELECT count(*) FROM conversation_history")).scalar_one()
    assert rows == 0, "something is writing conversation_history — it should be tested"


# --- Health probes ---


def test_health_is_unauthenticated_and_cheap(client):
    response = client.get("/health")
    assert_status(response, 200)
    assert response.json() == {"status": "ok"}


def test_readiness_checks_the_database(client):
    response = client.get("/health/ready")
    assert_status(response, 200)
    assert response.json() == {"status": "ready"}


def test_the_openapi_schema_is_generated(client):
    """A broken response model breaks schema generation before it breaks a
    client, so this is a cheap smoke test over every declared route."""
    response = client.get("/openapi.json")
    assert_status(response, 200)
    schema = response.json()
    assert schema["info"]["title"] == "AgentDesk API"
    assert len(schema["paths"]) >= 30, f"only {len(schema['paths'])} paths in the schema"
