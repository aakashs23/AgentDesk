"""RBAC enforcement across the whole API surface (Doc 05 §6–7).

Two separate questions are tested here and they have different correct answers:

* **Role gate** — the caller's role may not use this endpoint at all → 403.
* **Row scope** — the endpoint is allowed, but the row is outside the caller's
  visibility → 404, never 403, so existence is not leaked.
"""

import uuid

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_forbidden, assert_hidden, assert_status
from tests.helpers.auth import API, ROLES, auth

MISSING = uuid.UUID(int=0)


# --- Endpoints gated purely by role ---

ADMIN_ONLY = [
    ("POST", "/users"),
    ("GET", "/admin/automation-rules"),
    ("POST", "/admin/automation-rules"),
    ("GET", "/admin/automation-logs"),
    ("POST", "/admin/automation-rules/preview"),
    ("GET", "/webhooks"),
    ("POST", "/webhooks"),
    ("GET", "/notification-templates"),
    ("POST", "/notification-templates"),
]

STAFF_ONLY = [
    ("POST", "/tags"),
    ("GET", "/dashboard/metrics"),
    ("POST", "/reports/generate"),
]


def _call(client, method: str, path: str, token: str):
    return client.request(method, f"{API}{path}", json={}, headers=auth(token))


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
@pytest.mark.parametrize("role", ["requester", "agent", "team_lead"])
def test_admin_only_endpoints_reject_every_other_role(client, tokens, method, path, role):
    assert_forbidden(_call(client, method, path, tokens[role]), f"{role} {method} {path}")


@pytest.mark.parametrize("role", ["requester", "agent"])
def test_user_directory_is_closed_to_requesters_and_agents(client, tokens, role):
    """GET /users is the one admin-area read a team lead also gets (Doc 05 §6)."""
    assert_forbidden(client.get(f"{API}/users", headers=auth(tokens[role])), f"{role} GET /users")


@pytest.mark.parametrize("method,path", ADMIN_ONLY + STAFF_ONLY)
def test_privileged_endpoints_reject_anonymous_callers(client, method, path):
    response = client.request(method, f"{API}{path}", json={})
    assert_status(response, 401, f"anonymous {method} {path}")


@pytest.mark.parametrize("method,path", STAFF_ONLY)
def test_staff_endpoints_reject_requesters(client, tokens, method, path):
    assert_forbidden(_call(client, method, path, tokens["requester"]), f"requester {method} {path}")


@pytest.mark.parametrize("path", ["/users", "/admin/automation-rules", "/webhooks"])
def test_admin_itself_is_allowed_through_the_same_gates(client, tokens, path):
    """Guards the guard: a 403-for-everyone bug would pass the tests above."""
    response = client.get(f"{API}{path}", headers=auth(tokens["admin"]))
    assert_status(response, 200, f"admin GET {path}")


# --- Ticket-level authorization ---


def test_requester_cannot_assign_a_ticket(client, tokens, user_ids):
    ticket = f.make_ticket(client, tokens["requester"])
    response = f.assign(client, tokens["requester"], ticket["id"], assignee_id=user_ids["agent"])
    assert_forbidden(response, "requester assigned a ticket")


def test_requester_cannot_escalate_merge_or_split(client, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    other = f.make_ticket(client, tokens["requester"])
    header = auth(tokens["requester"])
    assert_forbidden(client.post(f"{API}/tickets/{ticket['id']}/escalate", headers=header))
    assert_forbidden(
        client.post(
            f"{API}/tickets/{ticket['id']}/merge",
            json={"target_ticket_id": other["id"]},
            headers=header,
        )
    )
    assert_forbidden(
        client.post(
            f"{API}/tickets/{ticket['id']}/split",
            json={"subtickets": [{"subject": "a", "description": "b"}]},
            headers=header,
        )
    )


def test_requester_cannot_classify_their_own_ticket(client, tokens, db):
    """subject/description are theirs to edit; category/priority/queue are not."""
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    header = auth(tokens["requester"])

    allowed = client.patch(
        f"{API}/tickets/{ticket['id']}", json={"subject": "edited by owner"}, headers=header
    )
    assert_status(allowed, 200, "owner could not edit their own subject")

    for field, value in [
        ("priority_id", catalog["priorities"]["Critical"]),
        ("queue_id", catalog["queue_id"]),
        ("category_id", next(iter(catalog["categories"].values()))),
    ]:
        response = client.patch(
            f"{API}/tickets/{ticket['id']}", json={field: value}, headers=header
        )
        assert_forbidden(response, f"requester set {field}")


def test_status_history_is_restricted_to_leads_and_admins(client, tokens, db):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    path = f"{API}/tickets/{ticket['id']}/status-history"

    for role in ("requester", "agent"):
        assert_forbidden(client.get(path, headers=auth(tokens[role])), f"{role} read history")
    for role in ("team_lead", "admin"):
        assert_status(client.get(path, headers=auth(tokens[role])), 200, f"{role} read history")


def test_requester_cannot_write_an_internal_note(client, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    response = f.comment(client, tokens["requester"], ticket["id"], "secret", is_internal=True)
    assert_forbidden(response, "requester wrote an internal note")


def test_internal_notes_are_invisible_to_the_requester(client, tokens, db):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.comment(client, tokens["agent"], ticket["id"], "internal only", is_internal=True)
    f.comment(client, tokens["agent"], ticket["id"], "public reply")

    seen = client.get(f"{API}/tickets/{ticket['id']}/comments", headers=auth(tokens["requester"]))
    assert_status(seen, 200)
    bodies = [c["body"] for c in seen.json()]
    assert "internal only" not in bodies, "internal note leaked to the requester"
    assert "public reply" in bodies


# --- Row scoping: out-of-scope rows are hidden, not forbidden ---


def test_a_requester_cannot_see_another_requesters_ticket(client, db, tokens):
    victim = f.verified_requester(client, db)
    ticket = f.make_ticket(client, victim["token"])
    attacker = f.verified_requester(client, db)

    for method, path, body in [
        ("GET", f"/tickets/{ticket['id']}", None),
        ("PATCH", f"/tickets/{ticket['id']}", {"subject": "hijacked"}),
        ("GET", f"/tickets/{ticket['id']}/comments", None),
        ("POST", f"/tickets/{ticket['id']}/comments", {"body": "hijacked"}),
        ("PATCH", f"/tickets/{ticket['id']}/status", {"status": "closed"}),
        ("POST", f"/tickets/{ticket['id']}/reopen", None),
    ]:
        response = client.request(
            method, f"{API}{path}", json=body, headers=auth(attacker["token"])
        )
        assert_hidden(response, f"{method} {path} leaked another requester's ticket")


def test_a_requesters_ticket_list_contains_only_their_own(client, db, tokens):
    owner = f.verified_requester(client, db)
    mine = f.make_ticket(client, owner["token"])
    f.make_ticket(client, tokens["requester"])  # someone else's

    listed = client.get(f"{API}/tickets", headers=auth(owner["token"]))
    assert_status(listed, 200)
    ids = {t["id"] for t in listed.json()}
    assert ids == {mine["id"]}, "ticket list crossed requester boundaries"


def test_missing_and_out_of_scope_are_indistinguishable(client, db):
    """Both must be 404 — a 403 on one and 404 on the other is an oracle."""
    victim = f.verified_requester(client, db)
    real = f.make_ticket(client, victim["token"])
    attacker = f.verified_requester(client, db)

    hidden = client.get(f"{API}/tickets/{real['id']}", headers=auth(attacker["token"]))
    absent = client.get(f"{API}/tickets/{MISSING}", headers=auth(attacker["token"]))
    assert hidden.status_code == absent.status_code == 404
    assert hidden.json() == absent.json(), "existing-but-hidden differs from truly missing"


def test_saved_views_are_private_to_their_owner(client, db, tokens):
    owner = f.verified_requester(client, db)
    created = client.post(
        f"{API}/saved-views",
        json={"name": f.rand("view-"), "filters": {"status": "new"}},
        headers=auth(owner["token"]),
    )
    assert_status(created, 201)
    view_id = created.json()["id"]

    for role in ROLES:  # not even an admin may read another user's saved view
        for method, body in [("GET", None), ("PATCH", {"name": "stolen"}), ("DELETE", None)]:
            if method == "GET":
                listed = client.get(f"{API}/saved-views", headers=auth(tokens[role]))
                assert view_id not in {v["id"] for v in listed.json()}
                continue
            response = client.request(
                method, f"{API}/saved-views/{view_id}", json=body, headers=auth(tokens[role])
            )
            assert_hidden(response, f"{role} {method} another user's saved view")


def test_notifications_are_private_to_their_recipient(client, db, tokens, user_ids):
    import sqlalchemy as sa

    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    # Assigning to the agent writes the agent a notification row.
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])

    with db.connect() as conn:
        notification_id = conn.execute(
            sa.text(
                "SELECT id FROM notifications WHERE user_id = :u ORDER BY created_at DESC LIMIT 1"
            ),
            {"u": user_ids["agent"]},
        ).scalar()
    assert notification_id, "assignment did not notify the assignee"

    response = client.patch(
        f"{API}/notifications/{notification_id}/read", headers=auth(tokens["requester"])
    )
    assert_hidden(response, "read another user's notification")


def test_generated_reports_are_private_to_their_creator(client, tokens):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["agent"]),
    )
    assert_status(created, 202)
    report_id = created.json()["id"]
    for role in ("team_lead", "admin"):
        response = client.get(f"{API}/reports/{report_id}", headers=auth(tokens[role]))
        assert_hidden(response, f"{role} read another user's report")


def test_team_lead_user_listing_is_limited_to_their_team(client, db, tokens, user_ids):
    """Doc 05 §6: leads see their own team, admins see everyone."""
    outsider = f.verified_requester(client, db)  # requesters have no team

    lead_view = client.get(f"{API}/users", headers=auth(tokens["team_lead"]))
    admin_view = client.get(f"{API}/users", headers=auth(tokens["admin"]))
    assert_status(lead_view, 200)
    assert_status(admin_view, 200)

    lead_ids = {u["id"] for u in lead_view.json()}
    admin_ids = {u["id"] for u in admin_view.json()}
    assert outsider["user"]["id"] in admin_ids
    assert outsider["user"]["id"] not in lead_ids, "lead saw a user outside their team"
    assert lead_ids < admin_ids


def test_a_user_cannot_read_an_unrelated_users_profile(client, db, tokens):
    other = f.verified_requester(client, db)
    response = client.get(f"{API}/users/{other['user']['id']}", headers=auth(tokens["requester"]))
    assert_forbidden(response, "requester read another user's profile")


def test_a_user_can_always_read_their_own_profile(client, tokens, user_ids):
    for role in ROLES:
        response = client.get(f"{API}/users/{user_ids[role]}", headers=auth(tokens[role]))
        assert_status(response, 200, f"{role} could not read their own profile")
