"""Reporting defects.

Reports are generated in a background task, so a broken generator does not
surface as an error response — `POST /reports/generate` returns 202 either way
and the failure is only visible by polling the report afterwards. That makes
these easy to ship unnoticed, and the pre-existing suite did exactly that: its
parametrised report test covered three of the five generators.
"""

from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth


def test_the_category_analytics_report_completes(client, tokens):
    """BUG-21 (Medium): `category_analytics` fails 100% of the time.

    Root cause: in `app/reporting/service._category_analytics`, the statement is

        sa.select(Category.name, sa.func.count())
          .join(Category, Category.id == Ticket.category_id, isouter=True)

    The only entity in the columns clause is `Category`, so SQLAlchemy infers
    `Category` as the left side of the FROM and is then asked to join `Category`
    to itself. It cannot compile the statement and raises
    `InvalidRequestError: Don't know how to join to <Mapper Category>`.

    The sibling generators get away with the same shape by accident:
    `_sla_compliance` also selects `Priority.name` and joins `Priority`, but its
    aggregate filters reference `Ticket`, which puts `Ticket` into the inferred
    FROM list and resolves the ambiguity. `_category_analytics` has no such
    reference, so nothing anchors the query to `tickets`.

    Because generation happens in a background task the API still answers 202,
    and the caller only discovers the failure on the next poll — where the
    message is a SQLAlchemy internal error rather than anything actionable.

    Fix: one line — make the left side explicit with `.select_from(Ticket)`
    before the `.join(...)`. Verified to compile to the intended
    `FROM tickets LEFT OUTER JOIN categories ON ...`.

    Worth doing alongside: have `generate()` log the exception rather than only
    storing `str(exc)` on the report, so a failing generator is visible in the
    logs and not just to whoever polls.
    """
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "category_analytics"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 202)

    report = client.get(
        f"{API}/reports/{created.json()['id']}", headers=auth(tokens["admin"])
    ).json()
    assert report["status"] == "ready", f"report failed: {report['error']}"
    assert report["columns"] == ["category", "count"]


def test_a_failed_report_does_not_leak_internals_to_the_client(client, tokens):
    """BUG-22 (Low): a failed report returns the raw exception text.

    `service.generate` stores `str(exc)` on the report and `GET /reports/{id}`
    hands it to the client verbatim. For BUG-21 that string is

        Don't know how to join to <Mapper at 0x10e27cd10; Category>. ...

    which exposes the ORM class layout and a live memory address — the same
    class of detail the global exception handler deliberately withholds by
    returning a generic 500 for unhandled errors. The background path bypasses
    that handler entirely, so the protection does not apply.

    Fix: log the exception server-side (as everywhere else does) and store a
    stable, non-revealing message on the report for the client to read.
    """
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "category_analytics"},
        headers=auth(tokens["admin"]),
    )
    report = client.get(
        f"{API}/reports/{created.json()['id']}", headers=auth(tokens["admin"])
    ).json()
    error = report["error"] or ""
    assert "Mapper at 0x" not in error, (
        f"the failure message exposes ORM internals and a memory address: {error}"
    )
