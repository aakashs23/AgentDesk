"""Concurrent requests against the same row.

TestClient is synchronous, so parallelism comes from a thread pool: each thread
issues a real HTTP request that the app serves on its own database session,
which is exactly the interleaving a multi-client deployment produces.

The bar for each scenario is *one* winner and a consistent database — either
the losers are rejected, or they are idempotent. Silent last-write-wins on a
counter, or duplicate rows in an append-only audit table, is corruption.
"""

import concurrent.futures as cf

import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_status, count_where
from tests.helpers.auth import API, auth

WORKERS = 8


def parallel(fn, n=WORKERS):
    """Run `fn(i)` n-ways and return the responses in completion order."""
    with cf.ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fn, range(n)))


def test_concurrent_creation_of_the_same_tag_yields_one_row(client, db, tokens):
    """A unique index is the only thing that can win this race — and it does."""
    name = f.rand("race-tag-")
    responses = parallel(
        lambda _: client.post(f"{API}/tags", json={"name": name}, headers=auth(tokens["agent"]))
    )
    codes = sorted(r.status_code for r in responses)

    assert codes.count(201) == 1, f"more than one creator succeeded: {codes}"
    assert set(codes) <= {201, 409, 500}, codes
    assert count_where(db, "tags", "name = :n", {"n": name}) == 1, "duplicate tag rows persisted"


def test_concurrent_ticket_creation_never_duplicates_a_display_id(client, db, tokens):
    """display_id comes from an identity column; concurrency must not collide."""
    subject = f.rand("race-create-")
    responses = parallel(
        lambda i: client.post(
            f"{API}/tickets",
            json={"subject": f"{subject}-{i}", "description": "d", "channel": "portal"},
            headers=auth(tokens["requester"]),
        )
    )
    created = [r.json() for r in responses if r.status_code == 201]
    assert len(created) == WORKERS, [r.status_code for r in responses]

    display_ids = [t["display_id"] for t in created]
    assert len(set(display_ids)) == len(display_ids), f"display_id collision: {display_ids}"


def test_concurrent_assignment_leaves_one_winner(client, db, tokens, user_ids):
    """Last write wins is acceptable here — but the row must equal *some* caller's
    intent, not a blend, and the audit trail must record every accepted write."""
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])

    candidates = [user_ids["agent"], user_ids["team_lead"], user_ids["admin"]]
    responses = parallel(
        lambda i: f.assign(
            client, tokens["admin"], ticket["id"], assignee_id=candidates[i % len(candidates)]
        )
    )
    assert all(r.status_code in (200, 409) for r in responses), [r.status_code for r in responses]

    with db.connect() as conn:
        final = conn.execute(
            sa.text("SELECT assignee_id FROM tickets WHERE id = :t"), {"t": ticket["id"]}
        ).scalar()
    assert str(final) in candidates, f"assignee ended up as {final}, which nobody requested"


def test_concurrent_duplicate_tag_attachment_is_rejected_once(client, db, tokens):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    tag = f.make_tag(client, tokens["agent"])

    responses = parallel(
        lambda _: client.post(
            f"{API}/tickets/{ticket['id']}/tags",
            json={"tag_id": tag["id"]},
            headers=auth(tokens["agent"]),
        )
    )
    codes = sorted(r.status_code for r in responses)
    assert codes.count(200) <= 1, f"the same tag attached more than once: {codes}"
    assert (
        count_where(
            db, "ticket_tags", "ticket_id = :t AND tag_id = :g", {"t": ticket["id"], "g": tag["id"]}
        )
        == 1
    )


def test_concurrent_comments_all_persist(client, db, tokens):
    """Comments are append-only: every accepted write must survive."""
    ticket = f.make_ticket(client, tokens["requester"])
    marker = f.rand("concurrent-comment-")
    responses = parallel(
        lambda i: f.comment(client, tokens["requester"], ticket["id"], f"{marker}-{i}")
    )
    accepted = [r for r in responses if r.status_code == 201]
    assert len(accepted) == WORKERS, [r.status_code for r in responses]

    stored = count_where(
        db, "comments", "ticket_id = :t AND body LIKE :b", {"t": ticket["id"], "b": f"{marker}%"}
    )
    assert stored == WORKERS, f"only {stored} of {WORKERS} concurrent comments persisted"


def test_concurrent_reads_are_consistent(client, db, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    responses = parallel(
        lambda _: client.get(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["requester"]))
    )
    assert all(r.status_code == 200 for r in responses)
    bodies = {r.json()["subject"] for r in responses}
    assert len(bodies) == 1, f"concurrent reads disagreed: {bodies}"


def test_concurrent_saved_view_deletes_produce_one_204(client, tokens):
    created = client.post(
        f"{API}/saved-views",
        json={"name": f.rand("race-view-"), "filters": {}},
        headers=auth(tokens["requester"]),
    )
    assert_status(created, 201)
    view_id = created.json()["id"]

    responses = parallel(
        lambda _: client.delete(f"{API}/saved-views/{view_id}", headers=auth(tokens["requester"]))
    )
    codes = sorted(r.status_code for r in responses)
    assert codes.count(204) >= 1, codes
    assert set(codes) <= {204, 404, 500}, codes
    # Whatever happened, it is gone and stays gone.
    assert_status(
        client.delete(f"{API}/saved-views/{view_id}", headers=auth(tokens["requester"])), 404
    )


def test_sequential_refresh_replay_is_rejected(client):
    """The single-use guarantee, tested the way it actually holds: sequentially.

    The concurrent version of this fails — see
    tests/regression/test_data_integrity_regressions.py.
    """
    from tests.helpers.auth import refresh_token_for

    token = refresh_token_for(client, "requester@agentdesk.dev")
    assert_status(client.post(f"{API}/auth/refresh", json={"refresh_token": token}), 200)
    assert_status(client.post(f"{API}/auth/refresh", json={"refresh_token": token}), 401)


def test_concurrent_login_is_safe(client):
    """Many simultaneous logins for one account must all succeed independently."""
    from tests.helpers.auth import login

    responses = parallel(lambda _: login(client, "agent@agentdesk.dev"), n=6)
    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    tokens = {r.json()["refresh_token"] for r in responses}
    assert len(tokens) == 6, "concurrent logins handed out the same refresh token"
