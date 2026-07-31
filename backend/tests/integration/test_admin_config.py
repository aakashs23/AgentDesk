"""Admin configuration CRUD (Phase 12): teams, queues, categories, priorities,
SLA rules, the audit-log reader and KB deletion.

Three properties matter more than the happy paths, and each has its own section
below: only an Admin may write configuration at all; a delete never orphans a
row that something still points at; and every change lands in the audit trail,
which is Doc 06's Phase 12 checkpoint.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_forbidden, assert_status, assert_validation_error
from tests.helpers.auth import API, ROLES, auth

MISSING = "00000000-0000-0000-0000-000000000000"


def admin(tokens):
    return auth(tokens["admin"])


def create(client, tokens, path, body, expect=201):
    response = client.post(f"{API}/admin/{path}", json=body, headers=admin(tokens))
    assert_status(response, expect)
    return response.json() if expect < 300 else response


def cleanup(client, tokens, path, row_id):
    client.delete(f"{API}/admin/{path}/{row_id}", headers=admin(tokens))


# --- Teams ------------------------------------------------------------------


def test_team_crud_round_trip(client, tokens):
    team = create(client, tokens, "teams", {"name": f.rand("team-")})
    try:
        listed = client.get(f"{API}/admin/teams", headers=admin(tokens))
        assert_status(listed, 200)
        assert team["id"] in {t["id"] for t in listed.json()}

        renamed = client.patch(
            f"{API}/admin/teams/{team['id']}",
            json={"name": f.rand("renamed-")},
            headers=admin(tokens),
        )
        assert_status(renamed, 200)
        assert renamed.json()["name"] != team["name"]
    finally:
        assert_status(client.delete(f"{API}/admin/teams/{team['id']}", headers=admin(tokens)), 204)
    gone = client.patch(
        f"{API}/admin/teams/{team['id']}", json={"name": "x"}, headers=admin(tokens)
    )
    assert_status(gone, 404, "a deleted team is still addressable")


def test_a_team_with_members_cannot_be_deleted(client, db, tokens):
    """Deleting the team out from under a user would leave `users.team_id`
    dangling and silently widen or narrow their ticket scope."""
    team = create(client, tokens, "teams", {"name": f.rand("staffed-")})
    member = f.activated_user(client, db, tokens["admin"], "agent", team_id=team["id"])
    response = client.delete(f"{API}/admin/teams/{team['id']}", headers=admin(tokens))
    assert_status(response, 409)
    assert "in use" in response.json()["detail"]
    # and once nobody points at it, the same delete succeeds
    assert_status(
        client.patch(f"{API}/users/{member['id']}", json={"team_id": None}, headers=admin(tokens)),
        200,
    )
    assert_status(client.delete(f"{API}/admin/teams/{team['id']}", headers=admin(tokens)), 204)


def test_duplicate_team_names_are_rejected(client, tokens):
    name = f.rand("unique-")
    team = create(client, tokens, "teams", {"name": name})
    try:
        clash = create(client, tokens, "teams", {"name": name.upper()}, expect=409)
        assert "already exists" in clash.json()["detail"]
    finally:
        cleanup(client, tokens, "teams", team["id"])


# --- Queues -----------------------------------------------------------------


def test_queue_crud_and_team_reassignment(client, tokens):
    team = create(client, tokens, "teams", {"name": f.rand("qteam-")})
    queue = create(client, tokens, "queues", {"name": f.rand("queue-")})
    try:
        assert queue["team_id"] is None
        moved = client.patch(
            f"{API}/admin/queues/{queue['id']}",
            json={"team_id": team["id"]},
            headers=admin(tokens),
        )
        assert_status(moved, 200)
        assert moved.json()["team_id"] == team["id"]
    finally:
        cleanup(client, tokens, "queues", queue["id"])
        cleanup(client, tokens, "teams", team["id"])


def test_a_queue_holding_tickets_cannot_be_deleted(client, tokens, user_ids):
    queue = create(client, tokens, "queues", {"name": f.rand("busy-")})
    ticket = f.make_ticket(client, tokens["requester"])
    assert_status(f.assign(client, tokens["admin"], ticket["id"], queue_id=queue["id"]), 200)
    assert_status(client.delete(f"{API}/admin/queues/{queue['id']}", headers=admin(tokens)), 409)


def test_a_queue_cannot_join_a_team_that_does_not_exist(client, tokens):
    response = client.post(
        f"{API}/admin/queues",
        json={"name": f.rand("q-"), "team_id": MISSING},
        headers=admin(tokens),
    )
    assert_status(response, 404)


# --- Categories -------------------------------------------------------------


def test_category_tree_create_and_read_back(client, tokens):
    """Writes land here, reads come from the shared `/categories` endpoint —
    the admin screen and the New Ticket form must see the same tree."""
    parent = create(client, tokens, "categories", {"name": f.rand("parent-")})
    child = create(
        client, tokens, "categories", {"name": f.rand("child-"), "parent_id": parent["id"]}
    )
    try:
        listed = client.get(f"{API}/categories", headers=admin(tokens)).json()
        by_id = {c["id"]: c for c in listed}
        assert by_id[child["id"]]["parent_id"] == parent["id"]
    finally:
        cleanup(client, tokens, "categories", child["id"])
        cleanup(client, tokens, "categories", parent["id"])


def test_a_category_cannot_become_its_own_ancestor(client, tokens):
    """`_top_level_category_name` walks parents until it finds a root; a cycle
    turns every routing decision into an infinite loop."""
    a = create(client, tokens, "categories", {"name": f.rand("cyc-a-")})
    b = create(client, tokens, "categories", {"name": f.rand("cyc-b-"), "parent_id": a["id"]})
    try:
        response = client.patch(
            f"{API}/admin/categories/{a['id']}",
            json={"parent_id": b["id"]},
            headers=admin(tokens),
        )
        assert_validation_error(response)
        self_parent = client.patch(
            f"{API}/admin/categories/{a['id']}",
            json={"parent_id": a["id"]},
            headers=admin(tokens),
        )
        assert_validation_error(self_parent)
    finally:
        cleanup(client, tokens, "categories", b["id"])
        cleanup(client, tokens, "categories", a["id"])


def test_a_category_with_children_cannot_be_deleted(client, tokens):
    parent = create(client, tokens, "categories", {"name": f.rand("keep-")})
    child = create(
        client, tokens, "categories", {"name": f.rand("kid-"), "parent_id": parent["id"]}
    )
    try:
        assert_status(
            client.delete(f"{API}/admin/categories/{parent['id']}", headers=admin(tokens)), 409
        )
    finally:
        cleanup(client, tokens, "categories", child["id"])
        cleanup(client, tokens, "categories", parent["id"])


# --- Priorities -------------------------------------------------------------


def test_priority_create_validates_the_colour(client, tokens):
    """Doc 04's picker sends `#rrggbb`; anything else would reach the UI as a
    broken swatch rather than a rejected form."""
    for bad in ("red", "#fff", "#12345g", ""):
        response = client.post(
            f"{API}/admin/priorities",
            json={"name": f.rand("p-"), "rank": 5, "color_hex": bad},
            headers=admin(tokens),
        )
        assert_validation_error(response, f"colour {bad!r} was accepted")


def test_priority_crud_round_trip(client, tokens):
    priority = create(
        client, tokens, "priorities", {"name": f.rand("prio-"), "rank": 9, "color_hex": "#AABBCC"}
    )
    try:
        patched = client.patch(
            f"{API}/admin/priorities/{priority['id']}",
            json={"color_hex": "#112233", "rank": 8},
            headers=admin(tokens),
        )
        assert_status(patched, 200)
        assert patched.json()["color_hex"] == "#112233"
        assert patched.json()["rank"] == 8
    finally:
        cleanup(client, tokens, "priorities", priority["id"])


def test_a_priority_in_use_by_an_sla_rule_cannot_be_deleted(client, tokens):
    priority = create(
        client, tokens, "priorities", {"name": f.rand("used-"), "rank": 7, "color_hex": "#123456"}
    )
    rule = create(
        client,
        tokens,
        "sla-rules",
        {"priority_id": priority["id"], "response_minutes": 30, "resolution_minutes": 240},
    )
    try:
        assert_status(
            client.delete(f"{API}/admin/priorities/{priority['id']}", headers=admin(tokens)), 409
        )
    finally:
        cleanup(client, tokens, "sla-rules", rule["id"])
        cleanup(client, tokens, "priorities", priority["id"])


# --- SLA rules --------------------------------------------------------------


def test_sla_rule_crud_round_trip(client, tokens):
    priority = create(
        client, tokens, "priorities", {"name": f.rand("sla-p-"), "rank": 6, "color_hex": "#654321"}
    )
    rule = create(
        client,
        tokens,
        "sla-rules",
        {"priority_id": priority["id"], "response_minutes": 15, "resolution_minutes": 60},
    )
    try:
        listed = client.get(f"{API}/admin/sla-rules", headers=admin(tokens))
        assert_status(listed, 200)
        assert rule["id"] in {r["id"] for r in listed.json()}

        patched = client.patch(
            f"{API}/admin/sla-rules/{rule['id']}",
            json={"resolution_minutes": 120},
            headers=admin(tokens),
        )
        assert_status(patched, 200)
        assert patched.json()["resolution_minutes"] == 120
    finally:
        cleanup(client, tokens, "sla-rules", rule["id"])
        cleanup(client, tokens, "priorities", priority["id"])


def test_two_rules_cannot_cover_the_same_category_and_priority(client, tokens):
    """`timers.policy_for` resolves with `.limit(1)`, so a duplicate pair makes a
    ticket's deadline non-deterministic."""
    priority = create(
        client, tokens, "priorities", {"name": f.rand("dup-p-"), "rank": 4, "color_hex": "#0f0f0f"}
    )
    first = create(
        client,
        tokens,
        "sla-rules",
        {"priority_id": priority["id"], "response_minutes": 10, "resolution_minutes": 60},
    )
    try:
        clash = create(
            client,
            tokens,
            "sla-rules",
            {"priority_id": priority["id"], "response_minutes": 99, "resolution_minutes": 999},
            expect=409,
        )
        assert "already covers" in clash.json()["detail"]
    finally:
        cleanup(client, tokens, "sla-rules", first["id"])
        cleanup(client, tokens, "priorities", priority["id"])


def test_sla_minutes_must_be_positive_and_sane(client, tokens, db):
    catalog = f.catalog(db)
    priority_id = next(iter(catalog["priorities"].values()))
    for minutes in (0, -5, 999_999):
        response = client.post(
            f"{API}/admin/sla-rules",
            json={
                "priority_id": priority_id,
                "response_minutes": minutes,
                "resolution_minutes": 60,
            },
            headers=admin(tokens),
        )
        assert_validation_error(response, f"{minutes} minutes was accepted")


# --- Audit log reader -------------------------------------------------------


def test_every_configuration_change_reaches_the_audit_log(client, tokens):
    """Doc 06 Phase 12 checkpoint: create, update and delete all leave a row."""
    team = create(client, tokens, "teams", {"name": f.rand("audited-")})
    client.patch(
        f"{API}/admin/teams/{team['id']}", json={"name": f.rand("audited2-")}, headers=admin(tokens)
    )
    cleanup(client, tokens, "teams", team["id"])

    logs = client.get(
        f"{API}/admin/audit-logs",
        params={"entity_type": "team", "entity_id": team["id"]},
        headers=admin(tokens),
    )
    assert_status(logs, 200)
    assert {row["action"] for row in logs.json()} == {"created", "updated", "deleted"}
    assert all(row["actor_id"] for row in logs.json()), "a config change lost its actor"


def test_audit_log_filters_narrow_rather_than_widen(client, tokens):
    team = create(client, tokens, "teams", {"name": f.rand("filter-")})
    try:
        everything = client.get(
            f"{API}/admin/audit-logs", params={"limit": 200}, headers=admin(tokens)
        ).json()
        by_type = client.get(
            f"{API}/admin/audit-logs",
            params={"entity_type": "team", "limit": 200},
            headers=admin(tokens),
        ).json()
        assert len(by_type) <= len(everything)
        assert {row["entity_type"] for row in by_type} == {"team"}

        types = client.get(f"{API}/admin/audit-logs/entity-types", headers=admin(tokens))
        assert_status(types, 200)
        assert "team" in types.json()
    finally:
        cleanup(client, tokens, "teams", team["id"])


def test_audit_log_is_newest_first(client, tokens):
    rows = client.get(f"{API}/admin/audit-logs", params={"limit": 50}, headers=admin(tokens)).json()
    timestamps = [row["created_at"] for row in rows]
    assert timestamps == sorted(timestamps, reverse=True)


# --- Knowledge base deletion ------------------------------------------------


def test_only_an_admin_may_delete_a_kb_article(client, db, tokens):
    created = client.post(
        f"{API}/knowledge-base/articles",
        json={"title": f.rand("doomed-"), "body": "body"},
        headers=auth(tokens["agent"]),
    )
    assert_status(created, 201)
    article_id = created.json()["id"]

    # its own author, an Agent, may not delete it
    assert_forbidden(
        client.delete(f"{API}/knowledge-base/articles/{article_id}", headers=auth(tokens["agent"]))
    )
    assert_status(
        client.delete(f"{API}/knowledge-base/articles/{article_id}", headers=admin(tokens)), 204
    )
    assert_status(
        client.get(f"{API}/knowledge-base/articles/{article_id}", headers=admin(tokens)), 404
    )


# --- RBAC: the whole surface is Admin-only ----------------------------------


CONFIG_WRITES = [
    ("POST", "/admin/teams", {"name": "x"}),
    ("POST", "/admin/queues", {"name": "x"}),
    ("POST", "/admin/categories", {"name": "x"}),
    ("POST", "/admin/priorities", {"name": "x", "rank": 1, "color_hex": "#000000"}),
    (
        "POST",
        "/admin/sla-rules",
        {"priority_id": MISSING, "response_minutes": 1, "resolution_minutes": 2},
    ),
    ("GET", "/admin/teams", None),
    ("GET", "/admin/queues", None),
    ("GET", "/admin/sla-rules", None),
    ("GET", "/admin/audit-logs", None),
]


@pytest.mark.parametrize("role", [r for r in ROLES if r != "admin"])
@pytest.mark.parametrize(
    "method,path,body", CONFIG_WRITES, ids=[f"{m} {p}" for m, p, _ in CONFIG_WRITES]
)
def test_non_admins_cannot_touch_configuration(client, tokens, role, method, path, body):
    response = client.request(method, f"{API}{path}", json=body, headers=auth(tokens[role]))
    assert_forbidden(response, f"{role} reached {method} {path}")
