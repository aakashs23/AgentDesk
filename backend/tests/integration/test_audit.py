"""The audit trail (Doc 05 Governance) and the dual-write invariant.

There is no audit-log *read* API yet (see test_api_surface.py), so these assert
directly against `audit_logs` and `ticket_status_history`. The invariant under
test is the one stated in CLAUDE.md: a status change writes to **both** tables,
always, and every mutating action leaves an attributable row behind.
"""

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_dual_trail, assert_status, count_where
from tests.helpers.auth import API, auth


def _audit_rows(db, entity_id, entity_type="ticket"):
    with db.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                sa.text(
                    "SELECT action, actor_id, before_state, after_state, created_at "
                    "FROM audit_logs WHERE entity_type = :e AND entity_id = :i "
                    "ORDER BY created_at"
                ),
                {"e": entity_type, "i": entity_id},
            ).mappings()
        ]


def _actions(db, entity_id, entity_type="ticket"):
    return [row["action"] for row in _audit_rows(db, entity_id, entity_type)]


# --- The dual-write invariant ---


def test_creation_writes_both_trails(client, db, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    assert "created" in _actions(db, ticket["id"])
    assert (
        count_where(
            db,
            "ticket_status_history",
            "ticket_id = :t AND new_status = 'new' AND old_status IS NULL",
            {"t": ticket["id"]},
        )
        == 1
    ), "creation did not write the initial — → new history row"


@pytest.mark.parametrize("status", ["open", "in_progress", "resolved", "closed"])
def test_every_status_change_writes_both_trails(client, db, tokens, status):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.drive_to(client, tokens, ticket["id"], status)
    assert_dual_trail(db, ticket["id"], status)


def test_reopen_writes_both_trails_and_the_automatic_re_entry(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.drive_to(client, tokens, ticket["id"], "closed")
    assert_status(
        client.post(f"{API}/tickets/{ticket['id']}/reopen", headers=auth(tokens["requester"])), 200
    )

    assert_dual_trail(db, ticket["id"], "reopened")
    # §10: the automatic reopened → in_progress hop is a system action (no actor)
    with db.connect() as conn:
        actor = conn.execute(
            sa.text(
                "SELECT changed_by FROM ticket_status_history WHERE ticket_id = :t "
                "AND old_status = 'reopened' AND new_status = 'in_progress'"
            ),
            {"t": ticket["id"]},
        ).scalar_one()
    assert actor is None, "the automatic re-entry was attributed to a user"


def test_a_merge_is_recorded_on_both_tickets(client, db, tokens):
    catalog = f.catalog(db)
    secondary = f.make_ticket(client, tokens["requester"])
    primary = f.make_ticket(client, tokens["requester"])
    for ticket in (secondary, primary):
        f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])

    assert_status(
        client.post(
            f"{API}/tickets/{secondary['id']}/merge",
            json={"target_ticket_id": primary["id"]},
            headers=auth(tokens["admin"]),
        ),
        200,
    )

    assert "merged" in _actions(db, secondary["id"]), "no merge audit row on the secondary"
    assert "merge_received" in _actions(db, primary["id"]), "no merge audit row on the primary"
    # The merge closes the secondary — the status history must show it.
    assert (
        count_where(
            db,
            "ticket_status_history",
            "ticket_id = :t AND new_status = 'closed'",
            {"t": secondary["id"]},
        )
        == 1
    )


def test_a_split_records_its_children(client, db, tokens):
    catalog = f.catalog(db)
    parent = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], parent["id"], queue_id=catalog["queue_id"])

    response = client.post(
        f"{API}/tickets/{parent['id']}/split",
        json={"subtickets": [{"subject": "part one", "description": "d"}]},
        headers=auth(tokens["admin"]),
    )
    assert_status(response, 201)
    child_ids = {c["id"] for c in response.json()}

    split_row = next(r for r in _audit_rows(db, parent["id"]) if r["action"] == "split")
    assert set(split_row["after_state"]["child_ticket_ids"]) == child_ids


# --- Attribution ---


def test_a_user_action_records_the_acting_user(client, db, tokens, user_ids):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    assert_status(
        f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"]), 200
    )

    assigned = next(r for r in _audit_rows(db, ticket["id"]) if r["action"] == "assigned")
    assert str(assigned["actor_id"]) == user_ids["admin"], "the wrong actor was recorded"


def test_a_system_action_records_no_actor(client, db, tokens):
    """Automation runs as the system, so `actor_id` must be null, not the
    triggering user — otherwise a rule's effects look like the user's edits."""
    catalog = f.catalog(db)
    marker = f.rand("audit-actor-")
    rule = f.make_rule(
        client,
        tokens["admin"],
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=[{"type": "set_priority", "priority_id": catalog["priorities"]["High"]}],
    )
    try:
        ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} auto")
        executed = [
            r for r in _audit_rows(db, ticket["id"]) if r["action"] == "automation_executed"
        ]
        assert executed, "the rule did not record an automation_executed audit row"
        assert all(r["actor_id"] is None for r in executed), "automation was attributed to a user"
    finally:
        f.delete_rule(client, tokens["admin"], rule["id"])


def test_before_and_after_state_are_both_captured(client, db, tokens, user_ids):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    assert_status(
        f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"]), 200
    )

    assigned = [r for r in _audit_rows(db, ticket["id"]) if r["action"] == "assigned"][-1]
    assert assigned["before_state"]["assignee_id"] == "None"
    assert assigned["after_state"]["assignee_id"] == user_ids["agent"]


@pytest.mark.parametrize(
    "entity_type,action",
    [("attachment", "uploaded"), ("attachment", "deleted")],
)
def test_attachment_lifecycle_is_audited(client, db, tokens, entity_type, action):
    ticket = f.make_ticket(client, tokens["requester"])
    uploaded = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": ("audit.png", b"\x89PNG" + b"\x00" * 32, "image/png")},
        headers=auth(tokens["requester"]),
    )
    assert_status(uploaded, 201)
    attachment_id = uploaded.json()["id"]

    if action == "deleted":
        assert_status(
            client.delete(f"{API}/attachments/{attachment_id}", headers=auth(tokens["admin"])), 204
        )

    assert action in _actions(db, attachment_id, entity_type), (
        f"no {entity_type}/{action} audit row"
    )


def test_admin_configuration_changes_are_audited(client, db, tokens, user_ids):
    rule = f.make_rule(client, tokens["admin"])
    try:
        client.patch(
            f"{API}/admin/automation-rules/{rule['id']}",
            json={"name": "audited rename"},
            headers=auth(tokens["admin"]),
        )
        actions = _actions(db, rule["id"], "automation_rule")
        assert "created" in actions and "updated" in actions, actions
        rows = _audit_rows(db, rule["id"], "automation_rule")
        assert all(str(r["actor_id"]) == user_ids["admin"] for r in rows)
    finally:
        f.delete_rule(client, tokens["admin"], rule["id"])


# --- Immutability ---


def test_the_audit_trail_is_append_only_through_the_api(client, db, tokens):
    """No endpoint may edit or remove an audit row. The strongest statement the
    API can make is that no such route exists at all."""
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    before = len(_audit_rows(db, ticket["id"]))

    for method, path in [
        ("DELETE", f"/audit-logs/{ticket['id']}"),
        ("PATCH", f"/audit-logs/{ticket['id']}"),
        ("POST", "/audit-logs"),
        ("DELETE", f"/tickets/{ticket['id']}/status-history"),
    ]:
        response = client.request(method, f"{API}{path}", json={}, headers=auth(tokens["admin"]))
        assert response.status_code in (404, 405), f"{method} {path}: {response.status_code}"

    assert len(_audit_rows(db, ticket["id"])) == before, "the audit trail changed"


def test_deleting_a_ticket_is_not_possible_through_the_api(client, tokens):
    """There is no ticket DELETE — closure and merge are the terminal states, so
    the trail can never be destroyed by removing its subject."""
    ticket = f.make_ticket(client, tokens["requester"])
    response = client.delete(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["admin"]))
    assert response.status_code in (404, 405), response.status_code


def test_status_history_is_ordered_and_complete(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.drive_to(client, tokens, ticket["id"], "closed")

    response = client.get(
        f"{API}/tickets/{ticket['id']}/status-history", headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    rows = response.json()

    assert [r["new_status"] for r in rows] == ["new", "open", "in_progress", "resolved", "closed"]
    assert rows[0]["old_status"] is None
    # Each row's old_status must be the previous row's new_status — no gaps.
    for previous, current in zip(rows, rows[1:], strict=False):
        assert current["old_status"] == previous["new_status"], (previous, current)
    assert [r["changed_at"] for r in rows] == sorted(r["changed_at"] for r in rows)
