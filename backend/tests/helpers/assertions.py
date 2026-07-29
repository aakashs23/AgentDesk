"""Reusable assertions.

Each one exists because the same check appears in several tests and the naked
version loses information on failure (a bare `assert r.status_code == 403` tells
you nothing about which body came back).
"""

import sqlalchemy as sa


def assert_status(response, expected: int, context: str = "") -> None:
    assert response.status_code == expected, (
        f"{context or response.request.url}: expected {expected}, "
        f"got {response.status_code} — {response.text[:400]}"
    )


def assert_forbidden(response, context: str = "") -> None:
    """403 for a caller who is authenticated but lacks the role."""
    assert_status(response, 403, context)


def assert_unauthorized(response, context: str = "") -> None:
    assert_status(response, 401, context)


def assert_hidden(response, context: str = "") -> None:
    """404, not 403 — an out-of-scope row must not leak its existence."""
    assert_status(response, 404, context)


def assert_validation_error(response, context: str = "") -> None:
    """422 from either Pydantic or a service-level guard."""
    assert response.status_code == 422, (
        f"{context or response.request.url}: expected 422, "
        f"got {response.status_code} — {response.text[:400]}"
    )


def assert_no_server_error(response, context: str = "") -> None:
    """The endpoint may reject the input, but must never crash on it."""
    assert response.status_code < 500, (
        f"{context or response.request.url}: server error {response.status_code} "
        f"— {response.text[:400]}"
    )


def assert_never_leaks_secrets(payload) -> None:
    """No response body may carry a hash, token, or raw secret field."""
    banned = {"password", "password_hash", "token_hash", "secret"}
    found: list[str] = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in banned:
                    found.append(f"{path}.{key}")
                walk(value, f"{path}.{key}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(payload)
    assert not found, f"response leaked sensitive field(s): {found}"


# --- Database-level assertions ---


def count_where(db, table: str, where: str, params: dict) -> int:
    with db.connect() as conn:
        return conn.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE {where}"), params
        ).scalar_one()


def assert_dual_trail(db, ticket_id: str, new_status: str) -> None:
    """The invariant: one status change writes BOTH history tables."""
    history = count_where(
        db,
        "ticket_status_history",
        "ticket_id = :t AND new_status = :s",
        {"t": ticket_id, "s": new_status},
    )
    audit = count_where(
        db,
        "audit_logs",
        "entity_type = 'ticket' AND entity_id = :t AND after_state->>'status' = :s",
        {"t": ticket_id, "s": new_status},
    )
    assert history >= 1, f"no ticket_status_history row for {new_status} on {ticket_id}"
    assert audit >= 1, f"no audit_logs row for {new_status} on {ticket_id}"


def assert_tables_intact(db, expected_tables=("users", "tickets", "roles", "audit_logs")) -> None:
    """After an injection attempt: the tables still exist and still have rows."""
    with db.connect() as conn:
        for table in expected_tables:
            exists = conn.execute(sa.text(f"SELECT to_regclass('public.{table}')")).scalar()
            assert exists, f"table {table} no longer exists"
        assert conn.execute(sa.text("SELECT count(*) FROM users")).scalar_one() > 0
        assert conn.execute(sa.text("SELECT count(*) FROM roles")).scalar_one() == 4
