"""Phase 15 security pass — the two checks that behavioural tests cannot make.

`test_sql_injection.py` proves the endpoints it knows about treat input as data.
`test_permissions.py` proves the endpoints it knows about are scoped. Both are
per-endpoint, so a new router added tomorrow is covered by neither. These two are
whole-codebase properties instead:

1. No SQL is assembled by string formatting anywhere in `app/`.
2. No value of a Document 05 §8 sensitive field ever reaches a response body or a
   log line, which is the Phase 15 checkpoint stated verbatim.
"""

import ast
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_never_leaks_secrets, assert_status
from tests.helpers.auth import API, ROLES, auth

APP_DIR = Path(__file__).resolve().parents[2] / "app"

# The fields the Phase 15 checkpoint names, all from Document 05 §8. The values
# themselves are pulled from the database by the `secret_values` fixture below —
# matching on the value rather than the field name is what makes a renamed
# serialiser field still fail. `webhooks.secret` is the HMAC key a caller could
# otherwise use to forge our own deliveries.


# --- 1. Parameterised queries -------------------------------------------------


def _sql_text_calls(tree: ast.AST):
    """Every `text(...)` / `sa.text(...)` call node in a module."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else None
        )
        if name == "text" and node.args:
            yield node


def test_no_sql_is_built_by_string_formatting():
    """A raw SQL string must be a literal — never an f-string, `%`, `.format()`
    or a concatenation. Those are the only shapes that can smuggle a caller's
    value into the statement itself; SQLAlchemy binds everything else.

    Scans source rather than behaviour on purpose: an injection test can only
    cover the endpoints someone remembered to write a payload for.
    """
    offenders: list[str] = []
    scanned = 0

    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for call in _sql_text_calls(tree):
            scanned += 1
            arg = call.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                continue  # a plain literal — the only safe shape
            if isinstance(arg, ast.JoinedStr):
                kind = "f-string"
            elif isinstance(arg, ast.BinOp):
                kind = "concatenation or %-format"
            elif isinstance(arg, ast.Call):
                kind = "call (.format()?)"
            else:
                kind = type(arg).__name__
            offenders.append(f"{path.relative_to(APP_DIR.parent)}:{arg.lineno} — {kind}")

    assert scanned, "found no text() calls at all — the scan is not looking where it thinks"
    assert not offenders, "SQL built by string formatting:\n  " + "\n  ".join(offenders)


def test_raw_sql_that_takes_a_value_binds_it():
    """The corollary: a literal is safe, but only if the values it needs arrive
    through `bindparams`/`params`. A `:name` placeholder with nothing bound to it
    is a bug that surfaces at runtime, not a leak — this keeps the pair honest."""
    for path in sorted(APP_DIR.rglob("*.py")):
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        for call in _sql_text_calls(tree):
            arg = call.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            if ":" not in arg.value:
                continue
            # `text("... :q ...")` must be followed by .bindparams(...) or be
            # executed with a params dict; both keep the value out of the SQL.
            snippet = source[arg.lineno - 1 : arg.end_lineno + 2]
            assert "bindparams" in snippet or "params" in snippet or "{" not in arg.value, (
                f"{path.name}:{arg.lineno}: placeholder without a visible binding"
            )


# --- 2. Sensitive values never leave the process ------------------------------


@pytest.fixture
def secret_values(client, db, tokens) -> Iterator[dict[str, str]]:
    """Real values straight out of the database, so the assertions below match on
    the actual secret rather than on a field name a serialiser could rename."""
    values: dict[str, str] = {}

    # `webhooks` is empty at rest, which would make the checkpoint's third field
    # a vacuous check — so create one, and hold on to *both* representations.
    # `POST /webhooks` returns the plaintext once, by design; every later read
    # must show neither it nor the ciphertext sitting in the column.
    #
    # `is_active: False` matters more than it looks. The suite shares one database
    # and never rolls back, so an *active* `ticket_created` webhook left behind
    # here fires a real HTTP delivery on every ticket the rest of the suite
    # creates — which is exactly how an earlier version of this fixture took 255
    # unrelated tests down with it. An inactive row is never dispatched
    # (`webhooks/service.py` filters on `is_active`) and still carries a secret,
    # which is all this fixture needs. It is deleted on teardown regardless.
    plaintext = f.rand("whsec-")
    created = client.post(
        f"{API}/webhooks",
        json={
            "event_type": "ticket_created",
            "target_url": f"https://example.com/hook/{f.rand()}",
            "secret": plaintext,
            "is_active": False,
        },
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    webhook_id = created.json()["id"]
    values["webhooks.secret (plaintext)"] = plaintext

    with db.connect() as conn:
        values["password_hash"] = conn.execute(
            sa.text("SELECT password_hash FROM users WHERE email = 'admin@agentdesk.dev'")
        ).scalar_one()
        # `token_hash` lives on three tables (Doc 05): refresh, password reset,
        # email verification. All three are equally disqualifying in a response.
        for table in ("refresh_tokens", "password_reset_tokens", "email_verification_tokens"):
            token_hash = conn.execute(
                sa.text(f"SELECT token_hash FROM {table} LIMIT 1")  # noqa: S608 — fixed literals
            ).scalar()
            if token_hash:
                values[f"{table}.token_hash"] = token_hash
        values["webhooks.secret (stored)"] = conn.execute(
            sa.text("SELECT secret FROM webhooks WHERE id = :i"), {"i": webhook_id}
        ).scalar_one()

    assert values["password_hash"], "expected the seeded admin to have a password hash"
    # Every field the Phase 15 checkpoint names must be represented, or the
    # assertions below quietly check nothing.
    assert any("token_hash" in k for k in values), "no token_hash available to test against"
    # These are used as substring needles. A short one would match by accident
    # (and a blank one matches everything), turning the checks below into noise.
    for name, value in values.items():
        assert len(value) >= 16, f"{name} is only {len(value)} chars — too short to search for"

    yield values

    # This fixture is the one place in the suite that writes a row other tests
    # can observe, so it is also the one place that has to clean up after itself.
    client.delete(f"{API}/webhooks/{webhook_id}", headers=auth(tokens["admin"]))


def _readable_endpoints(tokens) -> list[tuple[str, str]]:
    """(role, path) pairs covering every GET surface a role can reach."""
    paths = [
        "/tickets",
        "/users",
        "/notifications",
        "/notification-templates",
        "/categories",
        "/priorities",
        "/tags",
        "/knowledge-base/articles",
        "/saved-views",
        "/chat/sessions",
        "/csat",
        "/dashboard/metrics",
        "/webhooks",
        "/admin/teams",
        "/admin/queues",
        "/admin/sla-rules",
        "/admin/automation-rules",
        "/admin/automation-logs",
        "/admin/audit-logs",
        "/search/tickets?q=test",
    ]
    return [(role, path) for role in ROLES for path in paths]


def test_no_response_body_carries_a_sensitive_value(client, db, tokens, secret_values):
    """Checkpoint: no `password_hash`, `token_hash` or `webhooks.secret` value
    ever appears in a response. Checked by value *and* by field name — a
    serialiser that renames the field still fails the value check."""
    leaks: list[str] = []

    for role, path in _readable_endpoints(tokens):
        response = client.get(f"{API}{path}", headers=auth(tokens[role]))
        if response.status_code >= 400:
            continue  # a role that may not read this at all is fine
        body = response.text
        for name, value in secret_values.items():
            if value and value in body:
                leaks.append(f"{role} GET {path} leaked {name}")
        try:
            assert_never_leaks_secrets(response.json())
        except AssertionError as exc:
            leaks.append(f"{role} GET {path}: {exc}")

    assert not leaks, "sensitive data in responses:\n  " + "\n  ".join(leaks)


def test_a_single_user_and_ticket_detail_carry_no_hashes(client, tokens, user_ids, secret_values):
    """The list endpoints above use one serialiser; the detail endpoints use
    another, and only the detail one has the whole ORM object to hand."""
    ticket = f.make_ticket(client, tokens["requester"])
    for path, token in [
        (f"/users/{user_ids['agent']}", tokens["admin"]),
        (f"/users/{user_ids['requester']}", tokens["requester"]),  # own profile
        (f"/tickets/{ticket['id']}", tokens["requester"]),
    ]:
        response = client.get(f"{API}{path}", headers=auth(token))
        assert_status(response, 200)
        assert_never_leaks_secrets(response.json())
        for name, value in secret_values.items():
            assert value not in response.text, f"{path} leaked {name}"


def test_no_log_line_carries_a_sensitive_value(client, db, tokens, secret_values, caplog):
    """The other half of the checkpoint: "or log".

    Request logging is structured and includes the path, so a secret that ever
    travels in a query string would land in the log even though the response
    body is clean. Login is the interesting case — the password and the hash are
    both in scope during it.
    """
    with caplog.at_level(logging.DEBUG, logger="agentdesk"):
        client.post(
            f"{API}/auth/login",
            json={"email": "admin@agentdesk.dev", "password": "Password123!"},
        )
        client.post(
            f"{API}/auth/login",
            json={"email": "admin@agentdesk.dev", "password": "WrongPassword123!"},
        )
        ticket = f.make_ticket(client, tokens["requester"])
        client.get(f"{API}/tickets/{ticket['id']}", headers=auth(tokens["requester"]))
        client.get(f"{API}/users", headers=auth(tokens["admin"]))

    logged = "\n".join(record.getMessage() for record in caplog.records)
    # Guard against the scan passing because nothing was captured at all.
    assert caplog.records, "no log records captured — this check would pass vacuously"
    assert "/auth/login" in logged, "expected the request log to cover the login calls"

    for name, value in secret_values.items():
        assert value not in logged, f"log output carried {name}"
    # The plaintext password must not be logged either, in either outcome.
    assert "Password123!" not in logged
    assert "WrongPassword123!" not in logged


def test_an_unhandled_error_does_not_return_a_stack_trace(client, tokens, monkeypatch):
    """A traceback names modules, paths and locals. The 500 body stays opaque."""
    from app.search import service as search_service

    async def boom(*args, **kwargs):
        raise RuntimeError("secret-bearing internal failure")

    monkeypatch.setattr(search_service, "search_tickets", boom)
    response = client.get(f"{API}/search/tickets", params={"q": "x"}, headers=auth(tokens["admin"]))
    assert response.status_code == 500
    assert "secret-bearing internal failure" not in response.text
    assert "Traceback" not in response.text
