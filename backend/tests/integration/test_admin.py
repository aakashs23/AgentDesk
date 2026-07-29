"""Admin configuration: automation rules, webhooks, notification templates.

The automation *engine* is covered in test_automation.py; this file covers the
CRUD surface an admin drives, including the lifecycle rules that keep execution
history intact.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth

MISSING = "00000000-0000-0000-0000-000000000000"


# --- Automation rules ---


def test_rule_crud_round_trip(client, tokens):
    created = f.make_rule(client, tokens["admin"], name=f.rand("crud-"), priority=42)
    rule_id = created["id"]
    try:
        listed = client.get(f"{API}/admin/automation-rules", headers=auth(tokens["admin"]))
        assert_status(listed, 200)
        assert rule_id in {r["id"] for r in listed.json()}

        patched = client.patch(
            f"{API}/admin/automation-rules/{rule_id}",
            json={"name": "renamed", "priority": 7, "is_active": False},
            headers=auth(tokens["admin"]),
        )
        assert_status(patched, 200)
        assert patched.json()["name"] == "renamed"
        assert patched.json()["priority"] == 7
        assert patched.json()["is_active"] is False
    finally:
        assert_status(
            client.delete(f"{API}/admin/automation-rules/{rule_id}", headers=auth(tokens["admin"])),
            204,
        )
    gone = client.patch(
        f"{API}/admin/automation-rules/{rule_id}", json={"name": "x"}, headers=auth(tokens["admin"])
    )
    assert_status(gone, 404, "a deleted rule is still addressable")


def test_rules_are_listed_in_evaluation_order(client, tokens):
    """Lower priority number evaluates first — the list must reflect that."""
    low = f.make_rule(client, tokens["admin"], priority=90)
    high = f.make_rule(client, tokens["admin"], priority=10)
    try:
        listed = client.get(f"{API}/admin/automation-rules", headers=auth(tokens["admin"])).json()
        order = [r["id"] for r in listed]
        assert order.index(high["id"]) < order.index(low["id"]), "rules are not ordered by priority"
        assert [r["priority"] for r in listed] == sorted(r["priority"] for r in listed)
    finally:
        f.delete_rule(client, tokens["admin"], low["id"])
        f.delete_rule(client, tokens["admin"], high["id"])


def test_a_rule_with_execution_history_cannot_be_deleted(client, tokens):
    """Deleting would orphan `automation_execution_logs` rows, so it is refused
    in favour of deactivation."""
    rule = f.make_rule(client, tokens["admin"], conditions=[], actions=[])
    f.make_ticket(client, tokens["requester"])  # produces one execution log

    refused = client.delete(
        f"{API}/admin/automation-rules/{rule['id']}", headers=auth(tokens["admin"])
    )
    assert_status(refused, 409, "a rule with history was deleted")
    assert "deactivate" in refused.json()["detail"].lower()

    deactivated = client.patch(
        f"{API}/admin/automation-rules/{rule['id']}",
        json={"is_active": False},
        headers=auth(tokens["admin"]),
    )
    assert_status(deactivated, 200)
    assert deactivated.json()["is_active"] is False


def test_a_deactivated_rule_stops_firing(client, db, tokens):
    catalog = f.catalog(db)
    marker = f.rand("inactive-")
    rule = f.make_rule(
        client,
        tokens["admin"],
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=[{"type": "set_priority", "priority_id": catalog["priorities"]["Critical"]}],
        is_active=False,
    )
    try:
        ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} test")
        assert ticket["priority_id"] is None, "an inactive rule still fired"
    finally:
        f.delete_rule(client, tokens["admin"], rule["id"])


def test_the_preview_endpoint_matches_without_mutating(client, db, tokens):
    """§25 step 5: show which existing tickets a draft rule would match."""
    marker = f.rand("preview-")
    ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} candidate")

    response = client.post(
        f"{API}/admin/automation-rules/preview",
        json={"conditions": [{"field": "subject", "op": "contains", "value": marker}]},
        headers=auth(tokens["admin"]),
    )
    assert_status(response, 200)
    assert ticket["id"] in {t["id"] for t in response.json()}

    unchanged = client.get(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["admin"]))
    assert unchanged.json()["priority_id"] is None, "preview mutated the ticket"


def test_preview_rejects_an_unknown_condition_field(client, tokens):
    response = client.post(
        f"{API}/admin/automation-rules/preview",
        json={"conditions": [{"field": "password_hash", "op": "eq", "value": "x"}]},
        headers=auth(tokens["admin"]),
    )
    assert_status(response, 422)


def test_execution_logs_can_be_filtered(client, tokens):
    rule = f.make_rule(client, tokens["admin"], conditions=[], actions=[])
    ticket = f.make_ticket(client, tokens["requester"])

    by_rule = client.get(
        f"{API}/admin/automation-logs",
        params={"rule_id": rule["id"]},
        headers=auth(tokens["admin"]),
    )
    assert_status(by_rule, 200)
    assert by_rule.json(), "no execution log recorded for a rule that ran"
    assert {row["automation_rule_id"] for row in by_rule.json()} == {rule["id"]}

    by_ticket = client.get(
        f"{API}/admin/automation-logs",
        params={"ticket_id": ticket["id"]},
        headers=auth(tokens["admin"]),
    )
    assert_status(by_ticket, 200)
    assert {row["ticket_id"] for row in by_ticket.json()} == {ticket["id"]}

    f.delete_rule(client, tokens["admin"], rule["id"])


# --- Webhooks ---


@pytest.fixture
def webhook(client, tokens):
    created = client.post(
        f"{API}/webhooks",
        json={"event_type": "ticket_created", "target_url": "https://example.invalid/hook"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    yield created.json()
    client.delete(f"{API}/webhooks/{created.json()['id']}", headers=auth(tokens["admin"]))


def test_a_webhook_secret_is_generated_when_omitted(client, webhook):
    assert webhook["secret"], "no secret was generated"
    assert len(webhook["secret"]) >= 32


def test_a_supplied_webhook_secret_is_returned_verbatim_once(client, tokens):
    created = client.post(
        f"{API}/webhooks",
        json={
            "event_type": "status_changed",
            "target_url": "https://example.invalid/x",
            "secret": "my-own-secret",
        },
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    assert created.json()["secret"] == "my-own-secret"
    client.delete(f"{API}/webhooks/{created.json()['id']}", headers=auth(tokens["admin"]))


def test_a_webhook_secret_is_encrypted_at_rest(db, client, tokens):
    """Doc 05 Sensitive Fields: the column must not hold the plaintext."""
    import sqlalchemy as sa

    from app.webhooks import service as webhooks

    created = client.post(
        f"{API}/webhooks",
        json={
            "event_type": "sla_breached",
            "target_url": "https://example.invalid/y",
            "secret": "plaintext-secret-value",
        },
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    try:
        with db.connect() as conn:
            stored = conn.execute(
                sa.text("SELECT secret FROM webhooks WHERE id = :i"), {"i": created.json()["id"]}
            ).scalar_one()
        assert stored != "plaintext-secret-value", "the webhook secret is stored in plaintext"
        assert webhooks.decrypt_secret(stored) == "plaintext-secret-value"
    finally:
        client.delete(f"{API}/webhooks/{created.json()['id']}", headers=auth(tokens["admin"]))


def test_webhook_update_and_delete(client, tokens):
    created = client.post(
        f"{API}/webhooks",
        json={"event_type": "ticket_created", "target_url": "https://example.invalid/a"},
        headers=auth(tokens["admin"]),
    ).json()

    patched = client.patch(
        f"{API}/webhooks/{created['id']}",
        json={"target_url": "https://example.invalid/b", "is_active": False},
        headers=auth(tokens["admin"]),
    )
    assert_status(patched, 200)
    assert patched.json()["target_url"] == "https://example.invalid/b"
    assert patched.json()["is_active"] is False

    assert_status(
        client.delete(f"{API}/webhooks/{created['id']}", headers=auth(tokens["admin"])), 204
    )
    assert_status(
        client.get(f"{API}/webhooks/{created['id']}/deliveries", headers=auth(tokens["admin"])),
        404,
        "a deleted webhook still has an addressable delivery log",
    )


def test_delivery_history_is_readable(client, tokens, webhook):
    response = client.get(
        f"{API}/webhooks/{webhook['id']}/deliveries", headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert isinstance(response.json(), list)


# --- Notification templates ---


@pytest.fixture
def template(client, tokens):
    created = client.post(
        f"{API}/notification-templates",
        json={
            "trigger_type": "ticket_assigned",
            "channel": "in_app",
            "body_template": "Custom: {{ticket.display_id}} — {{ticket.subject}}",
        },
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    yield created.json()
    client.delete(
        f"{API}/notification-templates/{created.json()['id']}", headers=auth(tokens["admin"])
    )


def test_templates_are_seeded_for_every_trigger_and_channel(client, tokens):
    from app.notifications.templates import CHANNELS, NOTIFICATION_TRIGGERS

    listed = client.get(f"{API}/notification-templates", headers=auth(tokens["admin"]))
    assert_status(listed, 200)
    pairs = {(t["trigger_type"], t["channel"]) for t in listed.json()}
    for trigger in NOTIFICATION_TRIGGERS:
        for channel in CHANNELS:
            assert (trigger, channel) in pairs, f"no seeded template for {trigger}/{channel}"


def test_an_active_template_renders_the_notification(client, db, tokens, user_ids, template):
    """The most recently updated active template for the pair wins."""
    import sqlalchemy as sa

    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])

    with db.connect() as conn:
        payload = conn.execute(
            sa.text(
                "SELECT payload FROM notifications WHERE ticket_id = :t "
                "AND trigger_type = 'ticket_assigned' AND channel = 'in_app' LIMIT 1"
            ),
            {"t": ticket["id"]},
        ).scalar_one()
    assert f"AGT-{ticket['display_id']}" in payload["message"], payload
    assert ticket["subject"] in payload["message"]


def test_template_update_and_delete(client, tokens, template):
    patched = client.patch(
        f"{API}/notification-templates/{template['id']}",
        json={"body_template": "Updated body", "is_active": False},
        headers=auth(tokens["admin"]),
    )
    assert_status(patched, 200)
    assert patched.json()["body_template"] == "Updated body"
    assert patched.json()["is_active"] is False

    assert_status(
        client.delete(
            f"{API}/notification-templates/{template['id']}", headers=auth(tokens["admin"])
        ),
        204,
    )
    assert_status(
        client.patch(
            f"{API}/notification-templates/{template['id']}",
            json={"body_template": "x"},
            headers=auth(tokens["admin"]),
        ),
        404,
    )
