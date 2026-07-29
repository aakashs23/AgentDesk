"""Boundary values: empty, absent, extreme, and repeated.

Split from the security suites on purpose — nothing here is an attack. These are
the values a real client sends by accident: a null where a string was expected,
a retried request, a field left blank, a number at the edge of its range.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import (
    assert_no_server_error,
    assert_status,
    assert_validation_error,
)
from tests.helpers.auth import API, auth

MISSING_UUID = "00000000-0000-0000-0000-000000000000"


# --- Nulls and blanks ---


@pytest.mark.parametrize(
    "body",
    [
        {"subject": None, "description": "d", "channel": "portal"},
        {"subject": "s", "description": None, "channel": "portal"},
        {"subject": "s", "description": "d", "channel": None},
        {"subject": "s", "description": "d", "channel": "portal", "category_id": "not-a-uuid"},
    ],
)
def test_nulls_in_required_ticket_fields_are_rejected(client, tokens, body):
    assert_validation_error(
        client.post(f"{API}/tickets", json=body, headers=auth(tokens["requester"])), str(body)
    )


def test_an_explicit_null_category_is_accepted_as_absent(client, tokens):
    """`category_id: null` is meaningfully different from omitting it, and both
    must be treated as 'no category'."""
    response = client.post(
        f"{API}/tickets",
        json={
            "subject": f"null cat {f.rand()}",
            "description": "d",
            "channel": "portal",
            "category_id": None,
        },
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)
    assert response.json()["category_id"] is None


def test_an_empty_patch_body_is_a_no_op_not_an_error(client, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    response = client.patch(
        f"{API}/tickets/{ticket['id']}", json={}, headers=auth(tokens["requester"])
    )
    assert_status(response, 200, "empty PATCH")
    assert response.json()["subject"] == ticket["subject"]


def test_whitespace_only_text_is_accepted_as_written(client, tokens):
    """min_length=1 counts characters, not meaningful ones. Documented so a
    future trim-then-validate change is deliberate."""
    response = client.post(
        f"{API}/tickets",
        json={"subject": "   ", "description": "\t\n", "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_no_server_error(response, "whitespace-only text")


def test_assignment_with_neither_target_is_rejected(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    response = client.post(
        f"{API}/tickets/{ticket['id']}/assign", json={}, headers=auth(tokens["admin"])
    )
    assert_validation_error(response, "assign with no assignee and no queue")


# --- References to rows that do not exist ---


@pytest.mark.parametrize("field", ["category_id", "priority_id", "queue_id"])
def test_classifying_with_an_unknown_reference_is_rejected(client, tokens, field):
    ticket = f.make_ticket(client, tokens["requester"])
    response = client.patch(
        f"{API}/tickets/{ticket['id']}", json={field: MISSING_UUID}, headers=auth(tokens["agent"])
    )
    assert response.status_code in (404, 422), f"{field}: {response.status_code}"


def test_creating_a_ticket_in_an_unknown_category_is_rejected(client, tokens):
    response = client.post(
        f"{API}/tickets",
        json={
            "subject": "s",
            "description": "d",
            "channel": "portal",
            "category_id": MISSING_UUID,
        },
        headers=auth(tokens["requester"]),
    )
    assert_validation_error(response, "unknown category")


def test_assigning_to_an_unknown_user_is_rejected(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    response = f.assign(client, tokens["admin"], ticket["id"], assignee_id=MISSING_UUID)
    assert_validation_error(response, "unknown assignee")


def test_assigning_to_a_deactivated_user_is_rejected(client, db, tokens):
    catalog = f.catalog(db)
    agent = f.activated_user(client, db, tokens["admin"], "agent", team_id=catalog["team_id"])
    assert_status(client.delete(f"{API}/users/{agent['id']}", headers=auth(tokens["admin"])), 204)

    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    response = f.assign(client, tokens["admin"], ticket["id"], assignee_id=agent["id"])
    assert_validation_error(response, "assigned to a deactivated user")


def test_attaching_an_unknown_tag_is_a_404(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    response = client.post(
        f"{API}/tickets/{ticket['id']}/tags",
        json={"tag_id": MISSING_UUID},
        headers=auth(tokens["agent"]),
    )
    assert_status(response, 404, "unknown tag")


@pytest.mark.parametrize(
    "method,path",
    [
        # Resources with a read-by-id route
        ("GET", "/tickets/{id}"),
        ("GET", "/tickets/{id}/comments"),
        ("GET", "/attachments/{id}"),
        ("GET", "/reports/{id}"),
        ("GET", "/webhooks/{id}/deliveries"),
        # Resources whose only by-id routes are writes (no GET-by-id exists)
        ("PATCH", "/notifications/{id}/read"),
        ("PATCH", "/saved-views/{id}"),
        ("DELETE", "/saved-views/{id}"),
        ("PATCH", "/admin/automation-rules/{id}"),
        ("DELETE", "/admin/automation-rules/{id}"),
        ("PATCH", "/webhooks/{id}"),
        ("DELETE", "/webhooks/{id}"),
        ("PATCH", "/notification-templates/{id}"),
        ("DELETE", "/notification-templates/{id}"),
        ("DELETE", "/comments/{id}"),
    ],
)
def test_unknown_ids_return_404_not_500(client, tokens, method, path):
    url = f"{API}{path.format(id=MISSING_UUID)}"
    response = client.request(method, url, json={}, headers=auth(tokens["admin"]))
    assert response.status_code == 404, f"{method} {url}: {response.status_code}"


# --- Repeated / duplicate requests ---


def test_creating_the_same_tag_twice_is_a_conflict(client, tokens):
    name = f.rand("dup-tag-")
    first = client.post(f"{API}/tags", json={"name": name}, headers=auth(tokens["agent"]))
    second = client.post(f"{API}/tags", json={"name": name}, headers=auth(tokens["agent"]))
    assert_status(first, 201)
    assert_status(second, 409, "duplicate tag")


def test_attaching_the_same_tag_twice_is_a_conflict(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    tag = f.make_tag(client, tokens["agent"])
    body = {"tag_id": tag["id"]}

    assert_status(
        client.post(f"{API}/tickets/{ticket['id']}/tags", json=body, headers=auth(tokens["agent"])),
        200,
    )
    assert_status(
        client.post(f"{API}/tickets/{ticket['id']}/tags", json=body, headers=auth(tokens["agent"])),
        409,
        "duplicate tag attachment",
    )


def test_repeating_a_status_change_is_rejected_as_an_illegal_transition(client, db, tokens):
    """`open → open` is not in the §10 table, so a duplicate submit is a 409 —
    the retry is refused rather than double-writing the trail."""
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])

    assert_status(f.set_status(client, tokens["agent"], ticket["id"], "in_progress"), 200)
    repeat = f.set_status(client, tokens["agent"], ticket["id"], "in_progress")
    assert_status(repeat, 409, "repeated status change")


def test_marking_a_notification_read_twice_is_idempotent(client, db, tokens, user_ids):
    import sqlalchemy as sa

    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])

    with db.connect() as conn:
        notification_id = conn.execute(
            sa.text(
                "SELECT id FROM notifications WHERE user_id = :u ORDER BY created_at DESC LIMIT 1"
            ),
            {"u": user_ids["agent"]},
        ).scalar()

    for _ in range(3):
        response = client.patch(
            f"{API}/notifications/{notification_id}/read", headers=auth(tokens["agent"])
        )
        assert_status(response, 200, "repeat mark-read")
        assert response.json()["is_read"] is True


def test_deleting_a_saved_view_twice_returns_404_the_second_time(client, tokens):
    created = client.post(
        f"{API}/saved-views", json={"name": f.rand(), "filters": {}}, headers=auth(tokens["admin"])
    )
    view_id = created.json()["id"]
    assert_status(client.delete(f"{API}/saved-views/{view_id}", headers=auth(tokens["admin"])), 204)
    assert_status(client.delete(f"{API}/saved-views/{view_id}", headers=auth(tokens["admin"])), 404)


def test_reviewing_a_draft_twice_is_rejected(client, db, tokens):
    """Human-in-the-loop: a reviewed draft is final."""
    import uuid

    import sqlalchemy as sa

    ticket = f.make_ticket(client, tokens["requester"])
    draft_id = uuid.uuid4()
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO ai_draft_history (id, ticket_id, generated_by_model, draft_content) "
                "VALUES (:i, :t, 'test-model', 'draft body')"
            ),
            {"i": draft_id, "t": ticket["id"]},
        )

    body = {"action": "approved"}
    first = client.post(
        f"{API}/ai/drafts/{draft_id}/review", json=body, headers=auth(tokens["admin"])
    )
    assert_status(first, 200)
    second = client.post(
        f"{API}/ai/drafts/{draft_id}/review", json=body, headers=auth(tokens["admin"])
    )
    assert_status(second, 409, "re-reviewed an already-reviewed draft")


# --- Extremes that should be handled, not rejected ---


def test_a_large_but_reasonable_body_is_accepted(client, tokens):
    response = client.post(
        f"{API}/tickets",
        json={"subject": "log dump", "description": "x" * 20_000, "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201, "20k description")


def test_pagination_past_the_end_returns_an_empty_page(client, tokens):
    response = client.get(
        f"{API}/tickets", params={"offset": 1_000_000, "limit": 10}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert response.json() == []


def test_a_search_with_no_matches_returns_empty_lists_not_an_error(client, tokens):
    response = client.get(
        f"{API}/search/tickets",
        params={"q": f"zzz{f.rand()}zzz"},
        headers=auth(tokens["admin"]),
    )
    assert_status(response, 200)
    assert response.json()["tickets"] == []
    assert response.json()["kb_articles"] == []


def test_dashboard_metrics_are_well_formed_when_a_caller_has_no_data(client, db, tokens):
    """A brand-new agent's dashboard must render zeros, not nulls or a crash."""
    catalog = f.catalog(db)
    agent = f.activated_user(client, db, tokens["admin"], "agent", team_id=catalog["team_id"])
    response = client.get(f"{API}/dashboard/metrics", headers=auth(agent["token"]))
    assert_status(response, 200)

    body = response.json()
    assert isinstance(body["open_ticket_count"], int)
    assert isinstance(body["agent_workload"], list)
    # These are legitimately null with no resolved tickets — assert the key exists.
    assert "avg_resolution_seconds" in body
    assert "sla_compliance_rate" in body
