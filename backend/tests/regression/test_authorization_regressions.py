"""Authorization checks that are missing or too weak.

The RBAC primitives themselves hold up well — these are the places where an
operation is gated on *a* role but not on the specific relationship that makes
the operation meaningful.
"""

import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.auth import API, auth, refresh_token_for


def test_logout_only_revokes_a_token_belonging_to_the_caller(client, db, tokens):
    """BUG-9 (Medium): logout revokes any refresh token, not just the caller's.

    `service.logout` looks the token up by hash and revokes it without checking
    that `token.user_id` is the authenticated caller. Any authenticated user who
    obtains another user's refresh token — from a shared log, a proxy capture, a
    stale backup — can terminate that user's session on demand, repeatedly, with
    a valid session of their own as cover.

    Not privilege escalation, but a targeted denial of service against a
    specific account, and it makes session revocation unattributable.

    Fix: scope the UPDATE to the caller —
    `.where(RefreshToken.user_id == caller.id)` in `logout`, with the caller
    threaded through from the router (which already resolves `CurrentUser`).
    """
    victim = f.verified_requester(client, db)
    victim_refresh = refresh_token_for(client, victim["email"], victim["password"])
    attacker = f.verified_requester(client, db)

    client.post(
        f"{API}/auth/logout",
        json={"refresh_token": victim_refresh},
        headers=auth(attacker["token"]),
    )

    still_valid = client.post(f"{API}/auth/refresh", json={"refresh_token": victim_refresh})
    assert still_valid.status_code == 200, "another user's logout revoked this session"


def test_a_ticket_cannot_be_assigned_to_a_non_staff_user(client, db, tokens, user_ids):
    """BUG-5 (Medium): any user can be set as a ticket's assignee, including a
    requester.

    `service.assign_ticket` validates that the assignee exists and is active,
    but never that they hold a role which can actually work tickets. Assigning
    to a requester produces a ticket that its own assignee cannot see —
    `scope_tickets_to_caller` scopes requesters to `requester_id`, not
    `assignee_id` — so the ticket lands in nobody's queue while appearing
    assigned.

    It also pollutes reporting: `dashboard_metrics` joins `agent_workload` on
    `assignee_id` with no role filter, so a requester shows up as an agent
    carrying open tickets.

    Fix: resolve the assignee's role in `assign_ticket` and reject anything
    outside the existing `STAFF` set in `app/tickets/service.py` with a 422 —
    the constant and the role lookup are both already imported there.
    """
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])

    response = f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["requester"])
    assert response.status_code == 422, (
        f"assigning a ticket to a requester returned {response.status_code}"
    )


def test_a_requester_assignee_does_not_appear_in_agent_workload(client, db, tokens, user_ids):
    """BUG-5b (Low): the reporting consequence of BUG-5, stated separately so it
    stays covered even if assignment validation lands elsewhere."""
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=user_ids["requester"])

    metrics = client.get(f"{API}/dashboard/metrics", headers=auth(tokens["admin"]))
    assert metrics.status_code == 200, metrics.text
    workload_ids = {row["assignee_id"] for row in metrics.json()["agent_workload"]}
    assert user_ids["requester"] not in workload_ids, (
        "a requester is counted in agent workload metrics"
    )


def test_a_ticket_cannot_be_assigned_to_a_user_outside_the_queues_team(client, db, tokens):
    """BUG-11 (Low): assignment ignores team boundaries.

    A ticket sitting in Team A's queue can be assigned to an agent who belongs
    to Team B. The assignee can still see it (agents are scoped by
    `assignee_id` OR their team's queues), so it is not a data leak — but it
    routes work across teams with no check and no audit of the crossing, which
    the queue model exists to prevent.

    Fix: compare the assignee's `team_id` against the queue's in
    `assign_ticket`, rejecting a mismatch unless the caller is an admin.
    """
    catalog = f.catalog(db)
    outsider = f.activated_user(client, db, tokens["admin"], "agent", team_id=None)

    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    response = f.assign(client, tokens["admin"], ticket["id"], assignee_id=outsider["id"])
    assert response.status_code == 422, (
        f"assigned a queue's ticket to an agent on no team: {response.status_code}"
    )


def test_a_deactivated_users_tickets_are_reassigned_or_flagged(client, db, tokens):
    """BUG-12 (Low): deactivating a user orphans their open tickets.

    `deactivate_user` flips `is_active` and revokes refresh tokens, but leaves
    every open ticket pointing at an assignee who can no longer log in. Those
    tickets stay out of any queue-based view for agents whose team does not own
    the queue, and their SLA timers keep running with nobody able to act.

    Fix: in `deactivate_user`, null the `assignee_id` on the user's non-terminal
    tickets (and audit it) so they fall back to queue-level visibility.
    """
    catalog = f.catalog(db)
    agent = f.activated_user(client, db, tokens["admin"], "agent", team_id=catalog["team_id"])
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    f.assign(client, tokens["admin"], ticket["id"], assignee_id=agent["id"])

    assert (
        client.delete(f"{API}/users/{agent['id']}", headers=auth(tokens["admin"])).status_code
        == 204
    )

    with db.connect() as conn:
        assignee = conn.execute(
            sa.text("SELECT assignee_id FROM tickets WHERE id = :t"), {"t": ticket["id"]}
        ).scalar()
    assert assignee is None or str(assignee) != agent["id"], (
        "an open ticket is still assigned to a deactivated user"
    )
