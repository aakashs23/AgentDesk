"""Races and uniqueness gaps that let the database reach an inconsistent state.

These are the expensive class of bug: nothing errors, the API returns 200, and
the damage is only visible by reading the rows back. Each test asserts on
persisted state rather than on a status code, because every one of these
scenarios *looks* successful from the client side.
"""

import concurrent.futures as cf

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import count_where
from tests.helpers.auth import API, auth, refresh_token_for

pytestmark = pytest.mark.xfail(strict=True, reason="confirmed defect — see TEST_REPORT.md")

WORKERS = 6


def parallel(fn, n=WORKERS):
    with cf.ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fn, range(n)))


def test_concurrent_status_changes_write_one_history_row(client, db, tokens):
    """BUG-7 (High): the state machine has no concurrency control.

    `engine.transition` reads `ticket.status`, validates the (old, new) pair
    against the §10 table, then writes. Six simultaneous `open → in_progress`
    requests all read `open`, all validate, and all write — producing four
    accepted transitions and four `ticket_status_history` rows for a single
    logical change.

    That breaks the stated invariant that one status change writes exactly one
    row to each trail table, and it corrupts every downstream consumer:
    first-response time, `_hold_started_at` (which takes the newest `on_hold`
    row), and the audit trail an operator would rely on in a dispute.

    Fix: take a row lock before validating. In
    `app/tickets/service.get_ticket_scoped`, add `.with_for_update()` to the
    SELECT on the mutating paths so the second transaction blocks and then
    re-reads `in_progress`, failing the §10 check as it should.
    """
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])

    responses = parallel(
        lambda _: f.set_status(client, tokens["agent"], ticket["id"], "in_progress")
    )
    accepted = sum(1 for r in responses if r.status_code == 200)

    rows = count_where(
        db,
        "ticket_status_history",
        "ticket_id = :t AND new_status = 'in_progress'",
        {"t": ticket["id"]},
    )
    assert accepted == 1, f"{accepted} concurrent transitions were accepted, expected 1"
    assert rows == 1, f"{rows} history rows written for one logical status change"


def test_concurrent_reopens_keep_the_counter_consistent(client, db, tokens):
    """BUG-7b (High): lost updates on `tickets.reopened_count`.

    Same root cause as BUG-7, but the visible damage is a wrong number rather
    than a duplicate row. Five simultaneous reopens each read `reopened_count`
    as 0, each increment to 1, and the last write wins — so five accepted
    reopens leave the counter at 1. Each also starts a fresh SLA resolution
    segment, so the deadline reflects whichever transaction committed last.

    Fix: the same `SELECT ... FOR UPDATE` as BUG-7.
    """
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.drive_to(client, tokens, ticket["id"], "closed")

    responses = parallel(
        lambda _: client.post(
            f"{API}/tickets/{ticket['id']}/reopen", headers=auth(tokens["requester"])
        ),
        n=5,
    )
    accepted = sum(1 for r in responses if r.status_code == 200)

    with db.connect() as conn:
        counter = conn.execute(
            sa.text("SELECT reopened_count FROM tickets WHERE id = :t"), {"t": ticket["id"]}
        ).scalar_one()
    assert counter == accepted, (
        f"{accepted} reopens were accepted but reopened_count is {counter} — updates were lost"
    )


def test_a_refresh_token_cannot_be_replayed_concurrently(client):
    """BUG-8 (High): refresh rotation is single-use only when serialised.

    `rotate_refresh` reads the token row, checks `revoked_at is None`, then sets
    it. Six concurrent posts of the *same* token all pass the check before any
    of them commits, so five extra access/refresh pairs are minted from one
    single-use token.

    Impact is squarely on session security. An attacker who captures a refresh
    token can replay it in parallel with the victim's own client and hold live
    sessions indefinitely; rotation is supposed to make exactly that detectable
    and it does not.

    Fix: make the revoke the guard rather than a follow-up write — a conditional
    `UPDATE refresh_tokens SET revoked_at = now() WHERE token_hash = :h AND
    revoked_at IS NULL RETURNING user_id`, and treat zero rows as invalid. One
    statement, atomic, no lock needed.
    """
    token = refresh_token_for(client, "requester@agentdesk.dev")
    responses = parallel(
        lambda _: client.post(f"{API}/auth/refresh", json={"refresh_token": token})
    )
    accepted = sum(1 for r in responses if r.status_code == 200)
    assert accepted == 1, f"a single-use refresh token was accepted {accepted} times"


def test_email_addresses_are_unique_case_insensitively(client, db):
    """BUG-4 (Medium): two accounts can share one address in different cases.

    `_user_by_email` compares with `==` and registration stores whatever casing
    was submitted, so `user@example.com` and `USER@example.com` are two rows.
    Email addresses are case-insensitive in the domain part and, in practice,
    in the local part for every mainstream provider — so both accounts belong to
    the same human mailbox.

    Consequences: a password-reset link for either account lands in the same
    inbox; login is case-sensitive, so which account a person reaches depends on
    how they type it; and an attacker who knows a target's address can register
    the alternate casing to seed confusion.

    Fix: normalise once at the boundary. Lower-case the address in
    `RegisterRequest`/`UserCreate`/`LoginRequest` validators, and add a unique
    index on `lower(email)` so the database enforces it for existing paths too.
    """
    email = f.unique_email("case")
    first = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "First"},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{API}/auth/register",
        json={"email": email.upper(), "password": "Password123!", "full_name": "Second"},
    )
    assert second.status_code == 409, (
        f"registering {email.upper()} after {email} returned {second.status_code} — "
        "two accounts now share one mailbox"
    )


def test_login_is_case_insensitive_on_the_email(client, db):
    """BUG-4b (Medium): the same normalisation gap, seen from the login side.

    Even with one account, a user who types their address with different
    capitalisation than they registered with cannot log in at all.
    """
    user = f.verified_requester(client, db)
    from tests.helpers.auth import login

    response = login(client, user["email"].upper(), user["password"])
    assert response.status_code == 200, (
        f"login with an upper-cased address returned {response.status_code}"
    )


def test_a_failed_automation_rule_does_not_suppress_a_valid_one(client, db, tokens):
    """BUG-10 (Medium): a broken rule steals the conflict slot it never used.

    In `automation._execute_actions`, `_claim(...)` marks the slot for the rule
    *before* the action's target is validated. When a high-priority rule then
    raises (unknown priority id), the exception is caught and logged as failed —
    but the slot stays claimed. The next rule that wants the same field is
    treated as a §15 conflict and suppressed, so a perfectly valid rule silently
    never runs.

    The observable result: a ticket that should have been set to High priority
    keeps no priority at all, and the only trace is a `automation_conflict`
    audit row naming a rule that failed.

    Fix: validate before claiming — move the existence check above the `_claim`
    call in each action branch, so a rule that cannot execute never reserves the
    slot.
    """
    catalog = f.catalog(db)
    broken = f.make_rule(
        client,
        tokens["admin"],
        priority=1,
        actions=[{"type": "set_priority", "priority_id": "00000000-0000-0000-0000-000000000000"}],
    )
    valid = f.make_rule(
        client,
        tokens["admin"],
        priority=2,
        actions=[{"type": "set_priority", "priority_id": catalog["priorities"]["High"]}],
    )
    try:
        ticket = f.make_ticket(client, tokens["requester"])
        with db.connect() as conn:
            priority = conn.execute(
                sa.text("SELECT priority_id FROM tickets WHERE id = :t"), {"t": ticket["id"]}
            ).scalar()
        assert str(priority) == catalog["priorities"]["High"], (
            "the valid lower-priority rule was suppressed by a rule that failed"
        )
    finally:
        f.delete_rule(client, tokens["admin"], broken["id"])
        f.delete_rule(client, tokens["admin"], valid["id"])
