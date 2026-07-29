"""Automation condition operators and every action type.

test_automation.py covers the engine's dispatch/conflict/logging behaviour; this
file walks the vocabulary itself — each operator in `matches`, each branch in
`_execute_actions` — so an unhandled action type or a broken operator fails here
rather than silently in a `failed` execution log.
"""

import pytest
import sqlalchemy as sa

from app.models import Ticket
from app.workflow.automation import matches
from tests.helpers import factories as f
from tests.helpers.assertions import assert_status, count_where
from tests.helpers.auth import API, auth


def _ticket(**overrides) -> Ticket:
    defaults = {
        "subject": "Printer is on fire",
        "description": "Smoke everywhere",
        "status": "new",
        "channel": "portal",
    }
    return Ticket(requester_id=None, **{**defaults, **overrides})


# --- Condition operators (pure, no database) ---


@pytest.mark.parametrize(
    "condition,expected",
    [
        ({"field": "status", "op": "eq", "value": "new"}, True),
        ({"field": "status", "op": "eq", "value": "closed"}, False),
        ({"field": "status", "op": "ne", "value": "closed"}, True),
        ({"field": "status", "op": "ne", "value": "new"}, False),
        ({"field": "status", "op": "in", "value": ["new", "open"]}, True),
        ({"field": "status", "op": "in", "value": ["closed"]}, False),
        ({"field": "subject", "op": "contains", "value": "printer"}, True),
        ({"field": "subject", "op": "contains", "value": "PRINTER"}, True),
        ({"field": "subject", "op": "contains", "value": "scanner"}, False),
        ({"field": "channel", "op": "eq", "value": "portal"}, True),
        # An unset field compares as None rather than raising.
        ({"field": "assignee_id", "op": "eq", "value": None}, True),
        ({"field": "assignee_id", "op": "ne", "value": None}, False),
        # `op` defaults to eq when omitted.
        ({"field": "status", "value": "new"}, True),
    ],
)
def test_condition_operators(condition, expected):
    assert matches(_ticket(), [condition]) is expected


def test_conditions_are_anded_together():
    ticket = _ticket()
    assert matches(
        ticket, [{"field": "status", "value": "new"}, {"field": "channel", "value": "portal"}]
    )
    assert not matches(
        ticket, [{"field": "status", "value": "new"}, {"field": "channel", "value": "email"}]
    )


def test_an_empty_condition_list_matches_everything():
    assert matches(_ticket(), []) is True


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "password_hash", "op": "eq", "value": "x"},
        {"field": None, "op": "eq", "value": "x"},
        {"field": "status", "op": "regex", "value": "x"},
        {"field": "status", "op": "", "value": "x"},
    ],
)
def test_an_unknown_field_or_operator_raises(condition):
    """Raising is the contract — `dispatch` catches it and logs the rule failed."""
    with pytest.raises(ValueError):
        matches(_ticket(), [condition])


# --- Action types (through the API) ---


@pytest.fixture
def rule_cleanup(client, tokens):
    created: list[str] = []
    yield created.append
    for rule_id in created:
        f.delete_rule(client, tokens["admin"], rule_id)


def _fire(client, db, tokens, rule_cleanup, actions, marker=None):
    """Create a rule matching a unique marker, then a ticket that trips it."""
    marker = marker or f.rand("action-")
    rule = f.make_rule(
        client,
        tokens["admin"],
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=actions,
    )
    rule_cleanup(rule["id"])
    ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} trigger")
    return rule, ticket


def test_the_set_priority_action_applies(client, db, tokens, rule_cleanup):
    catalog = f.catalog(db)
    _rule, ticket = _fire(
        client,
        db,
        tokens,
        rule_cleanup,
        [{"type": "set_priority", "priority_id": catalog["priorities"]["Critical"]}],
    )
    assert ticket["priority_id"] == catalog["priorities"]["Critical"]


def test_the_assign_action_sets_the_queue_and_moves_new_to_open(
    client, db, tokens, rule_cleanup, user_ids
):
    catalog = f.catalog(db)
    _rule, ticket = _fire(
        client,
        db,
        tokens,
        rule_cleanup,
        [{"type": "assign", "queue_id": catalog["queue_id"], "assignee_id": user_ids["agent"]}],
    )
    assert ticket["queue_id"] == catalog["queue_id"]
    assert ticket["assignee_id"] == user_ids["agent"]
    assert ticket["status"] == "open", "rule-driven assignment did not move New → Open"


def test_the_add_tag_action_attaches_the_tag(client, db, tokens, rule_cleanup):
    tag = f.make_tag(client, tokens["agent"])
    _rule, ticket = _fire(
        client, db, tokens, rule_cleanup, [{"type": "add_tag", "tag_id": tag["id"]}]
    )
    assert (
        count_where(
            db,
            "ticket_tags",
            "ticket_id = :t AND tag_id = :g",
            {"t": ticket["id"], "g": tag["id"]},
        )
        == 1
    )


def test_the_add_tag_action_is_idempotent(client, db, tokens, rule_cleanup):
    """Two rules adding the same tag must not violate the composite primary key."""
    tag = f.make_tag(client, tokens["agent"])
    marker = f.rand("dup-tag-")
    for _ in range(2):
        rule = f.make_rule(
            client,
            tokens["admin"],
            conditions=[{"field": "subject", "op": "contains", "value": marker}],
            actions=[{"type": "add_tag", "tag_id": tag["id"]}],
        )
        rule_cleanup(rule["id"])

    ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} trigger")
    assert (
        count_where(
            db,
            "ticket_tags",
            "ticket_id = :t AND tag_id = :g",
            {"t": ticket["id"], "g": tag["id"]},
        )
        == 1
    )


def test_the_notify_action_writes_a_notification(client, db, tokens, rule_cleanup, user_ids):
    """The rule's `message` is a *fallback*, not an override.

    `notifications.notify` prefers an active template for the
    (trigger, channel) pair and only falls back to the caller's text when none
    exists. Seeding creates a template for every pair, so in a seeded system the
    rendered template always wins — see BUG-23 for why that makes the action's
    `message` parameter effectively dead.
    """
    _rule, ticket = _fire(
        client,
        db,
        tokens,
        rule_cleanup,
        [{"type": "notify", "user_id": user_ids["agent"], "message": "Custom automation message"}],
    )
    with db.connect() as conn:
        payload = conn.execute(
            sa.text(
                "SELECT payload FROM notifications WHERE ticket_id = :t "
                "AND trigger_type = 'automation_executed' AND user_id = :u "
                "AND channel = 'in_app' LIMIT 1"
            ),
            {"t": ticket["id"], "u": user_ids["agent"]},
        ).scalar_one_or_none()
    assert payload is not None, "the notify action produced no notification"
    assert f"AGT-{ticket['display_id']}" in payload["message"]


def test_the_notify_action_falls_back_to_its_own_message_without_a_template(
    client, db, tokens, rule_cleanup, user_ids
):
    """With the template deactivated, the rule's own message is what is stored."""
    listed = client.get(f"{API}/notification-templates", headers=auth(tokens["admin"])).json()
    template = next(
        t for t in listed if t["trigger_type"] == "automation_executed" and t["channel"] == "in_app"
    )
    assert_status(
        client.patch(
            f"{API}/notification-templates/{template['id']}",
            json={"is_active": False},
            headers=auth(tokens["admin"]),
        ),
        200,
    )
    try:
        _rule, ticket = _fire(
            client,
            db,
            tokens,
            rule_cleanup,
            [{"type": "notify", "user_id": user_ids["agent"], "message": "Fallback message"}],
        )
        with db.connect() as conn:
            payload = conn.execute(
                sa.text(
                    "SELECT payload FROM notifications WHERE ticket_id = :t "
                    "AND trigger_type = 'automation_executed' AND channel = 'in_app' LIMIT 1"
                ),
                {"t": ticket["id"]},
            ).scalar_one()
        assert payload["message"] == "Fallback message"
    finally:
        client.patch(
            f"{API}/notification-templates/{template['id']}",
            json={"is_active": True},
            headers=auth(tokens["admin"]),
        )


def test_the_escalate_action_reassigns_to_the_team_lead(client, db, tokens, rule_cleanup, user_ids):
    catalog = f.catalog(db)
    _rule, ticket = _fire(
        client,
        db,
        tokens,
        rule_cleanup,
        [
            {"type": "assign", "queue_id": catalog["queue_id"]},
            {"type": "escalate"},
        ],
    )
    assert ticket["assignee_id"] == user_ids["team_lead"], "escalate did not reach the team lead"
    assert (
        count_where(
            db,
            "notifications",
            "ticket_id = :t AND trigger_type = 'escalation' AND user_id = :u",
            {"t": ticket["id"], "u": user_ids["team_lead"]},
        )
        >= 1
    )


@pytest.mark.parametrize(
    "action",
    [
        {"type": "set_priority", "priority_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "assign", "queue_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "assign", "assignee_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "add_tag", "tag_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "not_a_real_action"},
    ],
)
def test_a_broken_action_is_logged_and_never_breaks_the_request(
    client, db, tokens, rule_cleanup, action
):
    """The whole point of the try/except in `dispatch`: a bad rule degrades to a
    `failed` log row, and ticket creation still returns 201."""
    rule, ticket = _fire(client, db, tokens, rule_cleanup, [action])

    logs = client.get(
        f"{API}/admin/automation-logs",
        params={"ticket_id": ticket["id"], "rule_id": rule["id"]},
        headers=auth(tokens["admin"]),
    )
    assert_status(logs, 200)
    statuses = [row["execution_status"] for row in logs.json()]
    assert statuses == ["failed"], f"expected one failed log, got {statuses}"
    assert logs.json()[0]["error_message"], "the failure was logged without a message"


def test_actions_do_not_cascade_into_another_trigger(client, db, tokens, rule_cleanup):
    """§15 keeps execution single-level: a rule that changes status must not
    re-fire status_changed rules, or two rules could loop forever."""
    catalog = f.catalog(db)
    marker = f.rand("cascade-")

    creator = f.make_rule(
        client,
        tokens["admin"],
        trigger_type="ticket_created",
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=[{"type": "assign", "queue_id": catalog["queue_id"]}],
    )
    rule_cleanup(creator["id"])
    watcher = f.make_rule(
        client,
        tokens["admin"],
        trigger_type="status_changed",
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=[{"type": "set_priority", "priority_id": catalog["priorities"]["Critical"]}],
    )
    rule_cleanup(watcher["id"])

    ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} trigger")

    # The assign moved New → Open, but that must not have run the watcher.
    assert ticket["status"] == "open"
    assert ticket["priority_id"] is None, "a rule action cascaded into another trigger"
    logs = client.get(
        f"{API}/admin/automation-logs",
        params={"ticket_id": ticket["id"], "rule_id": watcher["id"]},
        headers=auth(tokens["admin"]),
    )
    assert logs.json() == [], "the status_changed rule ran during ticket creation"
