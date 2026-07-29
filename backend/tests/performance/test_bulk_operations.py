"""Volume behaviour: bulk creation, list/search latency, and query counts.

Thresholds here are deliberately loose. This runs against a local Postgres on
developer hardware, so tight numbers would be flaky and would train people to
ignore the suite. What these catch is a *change in shape* — an endpoint that
goes from constant to linear, or a loop that starts issuing a query per row.

Marked `slow`; skip with `pytest -m "not slow"`.
"""

import time

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth

pytestmark = pytest.mark.slow


class Timer:
    """Wall-clock timing for a block, in milliseconds."""

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self.start) * 1000


class QueryCounter:
    """Counts SQL statements issued through the app's async engine.

    A blunt but effective N+1 detector: the count must not scale with the number
    of rows in the response.
    """

    def __init__(self):
        self.statements: list[str] = []

    def __enter__(self):
        from app.db import engine

        self._engine = engine.sync_engine

        def record(conn, cursor, statement, parameters, context, executemany):
            self.statements.append(statement)

        self._listener = record
        sa.event.listen(self._engine, "before_cursor_execute", record)
        return self

    def __exit__(self, *exc):
        sa.event.remove(self._engine, "before_cursor_execute", self._listener)

    def __len__(self):
        return len(self.statements)


# --- Bulk creation ---


@pytest.mark.parametrize("count", [100, 500])
def test_bulk_ticket_creation_stays_linear_and_consistent(client, db, tokens, count):
    """Create N tickets and check throughput, integrity, and identity uniqueness."""
    marker = f.rand("bulk-")
    with Timer() as timer:
        created = [
            client.post(
                f"{API}/tickets",
                json={"subject": f"{marker} {i}", "description": "load test", "channel": "portal"},
                headers=auth(tokens["requester"]),
            )
            for i in range(count)
        ]

    failures = [r.status_code for r in created if r.status_code != 201]
    assert not failures, f"{len(failures)} of {count} creations failed: {failures[:5]}"

    per_ticket_ms = timer.ms / count
    assert per_ticket_ms < 250, f"{per_ticket_ms:.1f}ms per ticket over {count} creations"

    # Integrity: every ticket persisted exactly once with a distinct display_id.
    with db.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT id, display_id FROM tickets WHERE subject LIKE :m"),
            {"m": f"{marker}%"},
        ).all()
    assert len(rows) == count, f"{len(rows)} rows persisted for {count} creations"
    assert len({r.display_id for r in rows}) == count, "duplicate display_id under load"


def test_a_thousand_tickets_do_not_degrade_the_list_endpoint(client, db, tokens):
    """List latency is bounded by the page size, not the table size."""
    with db.connect() as conn:
        total = conn.execute(sa.text("SELECT count(*) FROM tickets")).scalar_one()
    assert total > 500, f"only {total} tickets in the table — run the bulk test first"

    with Timer() as timer:
        response = client.get(
            f"{API}/tickets", params={"limit": 100}, headers=auth(tokens["admin"])
        )
    assert_status(response, 200)
    assert len(response.json()) == 100
    assert timer.ms < 1500, f"listing 100 of {total} tickets took {timer.ms:.0f}ms"


def test_deep_pagination_does_not_slow_down(client, tokens):
    """OFFSET scans are linear in Postgres; this pins how bad it is allowed to get."""
    with Timer() as first_page:
        client.get(
            f"{API}/tickets", params={"limit": 50, "offset": 0}, headers=auth(tokens["admin"])
        )
    with Timer() as deep_page:
        client.get(
            f"{API}/tickets", params={"limit": 50, "offset": 500}, headers=auth(tokens["admin"])
        )
    assert deep_page.ms < first_page.ms * 10 + 500, (
        f"page 1 took {first_page.ms:.0f}ms, page 11 took {deep_page.ms:.0f}ms"
    )


# --- Query counts (N+1 detection) ---


def test_listing_tickets_issues_a_constant_number_of_queries(client, tokens):
    """The count must not grow with the page size."""
    with QueryCounter() as small:
        client.get(f"{API}/tickets", params={"limit": 1}, headers=auth(tokens["admin"]))
    with QueryCounter() as large:
        client.get(f"{API}/tickets", params={"limit": 100}, headers=auth(tokens["admin"]))

    assert len(large) <= len(small) + 2, (
        f"{len(small)} queries for 1 ticket vs {len(large)} for 100 — N+1 in the list endpoint"
    )


def test_listing_users_is_not_n_plus_one_on_roles(client, tokens):
    """`to_user_out` resolves a role name per user; `role_name` caches the four
    roles, so a directory of N users must not issue N role lookups."""
    with QueryCounter() as counter:
        response = client.get(f"{API}/users", headers=auth(tokens["admin"]))
    assert_status(response, 200)
    user_count = len(response.json())
    assert user_count > 5, "not enough users to make this meaningful"
    assert len(counter) < user_count, (
        f"{len(counter)} queries for {user_count} users — the role cache is not working"
    )


def test_search_issues_a_bounded_number_of_queries(client, tokens):
    with QueryCounter() as counter:
        response = client.get(
            f"{API}/search/tickets",
            params={"q": "test", "limit": 50},
            headers=auth(tokens["admin"]),
        )
    assert_status(response, 200)
    assert len(counter) <= 6, f"search issued {len(counter)} queries for one request"


def test_the_dashboard_issues_a_bounded_number_of_queries(client, tokens):
    with QueryCounter() as counter:
        assert_status(client.get(f"{API}/dashboard/metrics", headers=auth(tokens["admin"])), 200)
    assert len(counter) <= 8, f"the dashboard issued {len(counter)} queries"


# --- Search and reporting under volume ---


def test_search_latency_is_acceptable_on_a_populated_table(client, db, tokens):
    with db.connect() as conn:
        total = conn.execute(sa.text("SELECT count(*) FROM tickets")).scalar_one()

    timings = []
    for term in ("bulk", "load test", "keyboard", "zzz-no-match"):
        with Timer() as timer:
            response = client.get(
                f"{API}/search/tickets", params={"q": term}, headers=auth(tokens["admin"])
            )
        assert_status(response, 200, term)
        timings.append((term, timer.ms))

    slowest = max(timings, key=lambda t: t[1])
    assert slowest[1] < 3000, f"search for {slowest[0]!r} took {slowest[1]:.0f}ms over {total} rows"


def test_the_search_index_is_actually_used(client, db):
    """A sequential scan here would mean migration 0001's GIN index is not being
    picked up — the query has to match the index expression exactly."""
    with db.connect() as conn:
        plan = "\n".join(
            row[0]
            for row in conn.execute(
                sa.text(
                    "EXPLAIN SELECT id FROM tickets WHERE "
                    "to_tsvector('english', subject || ' ' || description) "
                    "@@ plainto_tsquery('english', 'keyboard')"
                )
            )
        )
    assert "ix_tickets_fts" in plan or "Bitmap" in plan, (
        f"full-text search is not using an index:\n{plan}"
    )


def test_report_generation_scales_to_the_whole_table(client, db, tokens):
    with Timer() as timer:
        created = client.post(
            f"{API}/reports/generate",
            json={"report_type": "ticket_trends"},
            headers=auth(tokens["admin"]),
        )
        assert_status(created, 202)
        report = client.get(
            f"{API}/reports/{created.json()['id']}", headers=auth(tokens["admin"])
        ).json()

    assert report["status"] == "ready", report["error"]
    assert timer.ms < 5000, f"report generation took {timer.ms:.0f}ms"


def test_a_large_report_export_completes(client, tokens):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "agent_productivity"},
        headers=auth(tokens["admin"]),
    )
    with Timer() as timer:
        exported = client.get(
            f"{API}/reports/{created.json()['id']}/export",
            params={"format": "csv"},
            headers=auth(tokens["admin"]),
        )
    assert_status(exported, 200)
    assert timer.ms < 5000, f"CSV export took {timer.ms:.0f}ms"


# --- Payload size ---


def test_a_full_page_response_stays_a_reasonable_size(client, tokens):
    """A 100-ticket page carries every field including full descriptions; this
    pins the response size so a new field does not quietly blow it up."""
    response = client.get(f"{API}/tickets", params={"limit": 100}, headers=auth(tokens["admin"]))
    assert_status(response, 200)
    size_kb = len(response.content) / 1024
    assert size_kb < 512, f"a 100-ticket page is {size_kb:.0f}KB"


def test_uploading_at_the_size_cap_completes_promptly(client, tokens):
    from app.config import get_settings

    ticket = f.make_ticket(client, tokens["requester"])
    payload = b"\x89PNG" + b"\x00" * (get_settings().attachment_max_bytes - 4)

    with Timer() as timer:
        uploaded = client.post(
            f"{API}/tickets/{ticket['id']}/attachments",
            files={"file": ("large.png", payload, "image/png")},
            headers=auth(tokens["requester"]),
        )
    assert_status(uploaded, 201)
    assert timer.ms < 10_000, f"a 10MB upload took {timer.ms:.0f}ms"

    with Timer() as download_timer:
        downloaded = client.get(
            f"{API}/attachments/{uploaded.json()['id']}", headers=auth(tokens["requester"])
        )
    assert_status(downloaded, 200)
    assert len(downloaded.content) == len(payload), "the download was truncated"
    assert download_timer.ms < 10_000, f"a 10MB download took {download_timer.ms:.0f}ms"
