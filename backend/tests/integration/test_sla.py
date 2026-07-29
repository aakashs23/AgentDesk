"""SLA timers, pause/resume, breach detection and escalation (App Flow §16).

Timer *policy* is exercised through the API; the monitor loop is driven
directly, because waiting for its 60-second scan interval in a test would be
pure latency. Deadlines are manipulated in the database rather than by sleeping.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from app.db import _session_factory
from app.sla import monitor, timers
from tests.helpers import factories as f
from tests.helpers.assertions import assert_status, count_where
from tests.helpers.auth import API, auth


def _ticket_row(db, ticket_id):
    with db.connect() as conn:
        return (
            conn.execute(
                sa.text(
                    "SELECT response_due_at, resolution_due_at, resolved_at, closed_at, "
                    "status, assignee_id, reopened_count FROM tickets WHERE id = :t"
                ),
                {"t": ticket_id},
            )
            .mappings()
            .one()
        )


def _classified_ticket(client, db, tokens, priority="High"):
    """A ticket with a priority set, which is what starts the clocks."""
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    assert_status(
        client.patch(
            f"{API}/tickets/{ticket['id']}",
            json={"priority_id": catalog["priorities"][priority]},
            headers=auth(tokens["agent"]),
        ),
        200,
    )
    return ticket


# --- Timer creation ---


def test_an_unclassified_ticket_has_no_deadlines(client, db, tokens):
    """`sla_policies` keys on priority, so there is nothing to match yet."""
    ticket = f.make_ticket(client, tokens["requester"])
    row = _ticket_row(db, ticket["id"])
    assert row["response_due_at"] is None
    assert row["resolution_due_at"] is None


def test_classification_starts_both_clocks_anchored_at_creation(client, db, tokens):
    """§16: the clock conceptually started when the ticket arrived, not when an
    agent got round to classifying it."""
    ticket = _classified_ticket(client, db, tokens, "High")
    row = _ticket_row(db, ticket["id"])
    assert row["response_due_at"] is not None
    assert row["resolution_due_at"] is not None

    created_at = datetime.fromisoformat(ticket["created_at"])
    # Seeded policy for High: 60 minutes response, 480 resolution.
    assert row["response_due_at"] == created_at + timedelta(minutes=60)
    assert row["resolution_due_at"] == created_at + timedelta(minutes=480)


@pytest.mark.parametrize(
    "priority,response_minutes,resolution_minutes",
    [("Critical", 30, 240), ("High", 60, 480), ("Medium", 240, 1440), ("Low", 480, 2880)],
)
def test_each_priority_uses_its_own_policy(
    client, db, tokens, priority, response_minutes, resolution_minutes
):
    ticket = _classified_ticket(client, db, tokens, priority)
    row = _ticket_row(db, ticket["id"])
    created_at = datetime.fromisoformat(ticket["created_at"])
    assert row["response_due_at"] == created_at + timedelta(minutes=response_minutes)
    assert row["resolution_due_at"] == created_at + timedelta(minutes=resolution_minutes)


def test_reclassifying_never_restarts_a_running_clock(client, db, tokens):
    """Otherwise an agent could reset an SLA by re-picking the priority."""
    catalog = f.catalog(db)
    ticket = _classified_ticket(client, db, tokens, "Low")
    before = _ticket_row(db, ticket["id"])

    assert_status(
        client.patch(
            f"{API}/tickets/{ticket['id']}",
            json={"priority_id": catalog["priorities"]["Critical"]},
            headers=auth(tokens["agent"]),
        ),
        200,
    )
    after = _ticket_row(db, ticket["id"])
    assert after["resolution_due_at"] == before["resolution_due_at"], "the SLA clock was reset"


# --- Pause / resume ---


def test_on_hold_pauses_the_resolution_clock(client, db, tokens):
    """The deadline moves out by however long the ticket sat on hold."""
    ticket = _classified_ticket(client, db, tokens, "High")
    f.set_status(client, tokens["agent"], ticket["id"], "in_progress")
    assert_status(f.set_status(client, tokens["agent"], ticket["id"], "on_hold"), 200)

    before = _ticket_row(db, ticket["id"])["resolution_due_at"]
    # Backdate the hold so the resume has a measurable duration to add back.
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE ticket_status_history SET changed_at = changed_at - interval '2 hours' "
                "WHERE ticket_id = :t AND new_status = 'on_hold'"
            ),
            {"t": ticket["id"]},
        )

    assert_status(f.set_status(client, tokens["agent"], ticket["id"], "in_progress"), 200)
    after = _ticket_row(db, ticket["id"])["resolution_due_at"]

    extension = after - before
    assert timedelta(hours=1, minutes=55) < extension < timedelta(hours=2, minutes=5), (
        f"the hold extended the deadline by {extension}, expected about 2 hours"
    )


def test_the_paused_clock_is_not_extended_by_anything_else(client, db, tokens):
    """A status change that is not a hold-resume must leave the deadline alone."""
    ticket = _classified_ticket(client, db, tokens, "High")
    before = _ticket_row(db, ticket["id"])["resolution_due_at"]
    f.set_status(client, tokens["agent"], ticket["id"], "in_progress")
    assert _ticket_row(db, ticket["id"])["resolution_due_at"] == before


# --- Reopen ---


def test_reopening_starts_a_new_resolution_segment(client, db, tokens):
    """The invariant: reopen never resumes the original clock."""
    ticket = _classified_ticket(client, db, tokens, "High")
    f.drive_to(client, tokens, ticket["id"], "closed")
    original = _ticket_row(db, ticket["id"])["resolution_due_at"]

    reopened_at = datetime.now(UTC)
    assert_status(
        client.post(f"{API}/tickets/{ticket['id']}/reopen", headers=auth(tokens["requester"])), 200
    )
    row = _ticket_row(db, ticket["id"])

    assert row["resolution_due_at"] > original, "the old deadline was resumed"
    assert row["resolution_due_at"] - reopened_at == pytest.approx(
        timedelta(minutes=480), abs=timedelta(seconds=5)
    )
    assert row["reopened_count"] == 1
    assert row["resolved_at"] is None and row["closed_at"] is None
    assert row["status"] == "in_progress", "reopen should land in in_progress automatically"


def test_reopening_outside_the_window_is_refused(client, db, tokens):
    ticket = _classified_ticket(client, db, tokens, "High")
    f.drive_to(client, tokens, ticket["id"], "closed")
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE tickets SET closed_at = closed_at - interval '30 days' WHERE id = :t"),
            {"t": ticket["id"]},
        )
    response = client.post(
        f"{API}/tickets/{ticket['id']}/reopen", headers=auth(tokens["requester"])
    )
    assert_status(response, 409, "reopen long after closure")


# --- Monitor: warning and breach ---


def _scan(client) -> int:
    """One monitor pass, run on the app's own event loop (see run_on_app_loop)."""

    async def go() -> int:
        async with _session_factory() as session:
            fired = await monitor.scan_once(session)
            await session.commit()
            return fired

    return f.run_on_app_loop(client, go)


def _set_deadline(db, ticket_id, delta: timedelta):
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE tickets SET resolution_due_at = now() + :d WHERE id = :t"),
            {"d": delta, "t": ticket_id},
        )


def test_an_approaching_deadline_warns_the_assignee(client, db, tokens, user_ids):
    ticket = _classified_ticket(client, db, tokens, "High")
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])
    _set_deadline(db, ticket["id"], timedelta(minutes=5))  # inside the 30-minute warning window

    _scan(client)

    warned = count_where(
        db,
        "notifications",
        "ticket_id = :t AND trigger_type = 'sla_warning' AND user_id = :u",
        {"t": ticket["id"], "u": user_ids["agent"]},
    )
    assert warned >= 1, "no SLA warning was sent to the assignee"


def test_a_warning_fires_only_once_per_ticket(client, db, tokens, user_ids):
    ticket = _classified_ticket(client, db, tokens, "High")
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])
    _set_deadline(db, ticket["id"], timedelta(minutes=5))

    _scan(client)
    _scan(client)

    warnings = count_where(
        db,
        "notifications",
        "ticket_id = :t AND trigger_type = 'sla_warning' AND channel = 'in_app'",
        {"t": ticket["id"]},
    )
    assert warnings == 1, f"the warning fired {warnings} times across two scans"


def test_an_unassigned_ticket_is_not_warned(client, db, tokens):
    """§16 warns the assigned agent; there is nobody to warn yet."""
    ticket = _classified_ticket(client, db, tokens, "High")
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE tickets SET assignee_id = NULL WHERE id = :t"), {"t": ticket["id"]}
        )
    _set_deadline(db, ticket["id"], timedelta(minutes=5))

    _scan(client)
    assert (
        count_where(
            db,
            "notifications",
            "ticket_id = :t AND trigger_type = 'sla_warning'",
            {"t": ticket["id"]},
        )
        == 0
    )


def test_a_passed_deadline_escalates_to_the_team_lead(client, db, tokens, user_ids):
    ticket = _classified_ticket(client, db, tokens, "High")
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])
    _set_deadline(db, ticket["id"], timedelta(minutes=-10))

    _scan(client)

    row = _ticket_row(db, ticket["id"])
    assert str(row["assignee_id"]) == user_ids["team_lead"], "the breach did not escalate"

    assert (
        count_where(
            db,
            "notifications",
            "ticket_id = :t AND trigger_type = 'sla_breached' AND user_id = :u",
            {"t": ticket["id"], "u": user_ids["team_lead"]},
        )
        >= 1
    )
    assert (
        count_where(
            db,
            "audit_logs",
            "entity_type = 'ticket' AND entity_id = :t AND action = 'sla_escalated'",
            {"t": ticket["id"]},
        )
        >= 1
    )


def test_a_breach_escalates_only_once(client, db, tokens, user_ids):
    ticket = _classified_ticket(client, db, tokens, "High")
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])
    _set_deadline(db, ticket["id"], timedelta(minutes=-10))

    _scan(client)
    _scan(client)

    breaches = count_where(
        db,
        "notifications",
        "ticket_id = :t AND trigger_type = 'sla_breached' AND channel = 'in_app'",
        {"t": ticket["id"]},
    )
    assert breaches == 1, f"the breach fired {breaches} times across two scans"


@pytest.mark.parametrize("status", ["resolved", "closed"])
def test_terminal_tickets_are_not_scanned(client, db, tokens, user_ids, status):
    ticket = _classified_ticket(client, db, tokens, "High")
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])
    f.drive_to(client, tokens, ticket["id"], status)
    _set_deadline(db, ticket["id"], timedelta(minutes=-10))

    _scan(client)
    assert (
        count_where(
            db,
            "notifications",
            "ticket_id = :t AND trigger_type IN ('sla_warning', 'sla_breached')",
            {"t": ticket["id"]},
        )
        == 0
    ), f"a {status} ticket was still scanned for SLA breach"


def test_an_on_hold_ticket_is_not_scanned(client, db, tokens, user_ids):
    """The resolution clock is paused, so it cannot breach while held."""
    ticket = _classified_ticket(client, db, tokens, "High")
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["agent"])
    f.set_status(client, tokens["agent"], ticket["id"], "in_progress")
    f.set_status(client, tokens["agent"], ticket["id"], "on_hold")
    _set_deadline(db, ticket["id"], timedelta(minutes=-10))

    _scan(client)
    assert (
        count_where(
            db,
            "notifications",
            "ticket_id = :t AND trigger_type IN ('sla_warning', 'sla_breached')",
            {"t": ticket["id"]},
        )
        == 0
    )


def test_a_merged_ticket_is_not_scanned(client, db, tokens, user_ids):
    ticket = _classified_ticket(client, db, tokens, "High")
    target = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], target["id"], queue_id=f.catalog(db)["queue_id"])
    assert_status(
        client.post(
            f"{API}/tickets/{ticket['id']}/merge",
            json={"target_ticket_id": target["id"]},
            headers=auth(tokens["admin"]),
        ),
        200,
    )
    _set_deadline(db, ticket["id"], timedelta(minutes=-10))

    _scan(client)
    assert (
        count_where(
            db,
            "notifications",
            "ticket_id = :t AND trigger_type = 'sla_breached'",
            {"t": ticket["id"]},
        )
        == 0
    )


# --- Policy resolution ---


def test_a_category_specific_policy_wins_over_the_generic_one(client, db):
    """`policy_for` prefers an exact (category, priority) match."""

    async def go():
        async with _session_factory() as session:
            priority_id = (
                await session.execute(sa.text("SELECT id FROM priorities WHERE name = 'High'"))
            ).scalar_one()
            category_id = (
                await session.execute(sa.text("SELECT id FROM categories LIMIT 1"))
            ).scalar_one()

            specific_id = uuid.uuid4()
            await session.execute(
                sa.text(
                    "INSERT INTO sla_policies (id, category_id, priority_id, response_minutes, "
                    "resolution_minutes) VALUES (:i, :c, :p, 7, 11)"
                ),
                {"i": specific_id, "c": category_id, "p": priority_id},
            )
            await session.commit()
            try:
                specific = await timers.policy_for(session, category_id, priority_id)
                generic = await timers.policy_for(session, None, priority_id)
                return (
                    (specific.response_minutes, specific.resolution_minutes),
                    (generic.response_minutes, generic.resolution_minutes),
                )
            finally:
                await session.execute(
                    sa.text("DELETE FROM sla_policies WHERE id = :i"), {"i": specific_id}
                )
                await session.commit()

    specific, generic = f.run_on_app_loop(client, go)
    assert specific == (7, 11), "the generic policy won over the category-specific one"
    assert generic == (60, 480), "the category-specific policy leaked into the generic lookup"


def test_no_priority_means_no_policy(client):
    """sla_policies always keys on priority — an unclassified ticket matches none."""

    async def go():
        async with _session_factory() as session:
            return await timers.policy_for(session, None, None)

    assert f.run_on_app_loop(client, go) is None
