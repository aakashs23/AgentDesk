"""SQL injection attempts against every parameter that reaches a query.

The bar is not "no 500" — it is that the payload is treated as *data*: the
database survives intact, and a tautology like `' OR 1=1 --` never widens the
result set beyond what the caller is allowed to see.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import (
    assert_no_server_error,
    assert_status,
    assert_tables_intact,
    count_where,
)
from tests.helpers.auth import API, auth

PAYLOADS = [
    "' OR 1=1 --",
    "admin' --",
    '"; DROP TABLE users; --',
    "'; DROP TABLE tickets; --",
    "1' UNION SELECT NULL, version() --",
    "') OR ('1'='1",
    "'; UPDATE users SET role_id = (SELECT id FROM roles WHERE name='admin'); --",
    "\\'; SELECT pg_sleep(5); --",
    "%' OR '1'='1",
    "' OR ''='",
    "1; SELECT * FROM password_reset_tokens",
    "'||(SELECT password_hash FROM users LIMIT 1)||'",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_search_query_is_data_not_sql(client, db, tokens, payload):
    response = client.get(
        f"{API}/search/tickets", params={"q": payload}, headers=auth(tokens["admin"])
    )
    assert_no_server_error(response, f"search q={payload!r}")
    assert_tables_intact(db)
    if response.status_code == 200:
        body = response.json()
        assert body["query"] == payload, "the query was rewritten rather than parameterised"


@pytest.mark.parametrize("payload", PAYLOADS)
def test_login_email_is_data_not_sql(client, db, payload):
    response = client.post(
        f"{API}/auth/login", json={"email": f"a{payload}@example.com", "password": payload}
    )
    assert response.status_code in (401, 422), response.text
    assert_tables_intact(db)


@pytest.mark.parametrize("payload", PAYLOADS[:6])
def test_ticket_status_filter_is_data_not_sql(client, db, tokens, payload):
    response = client.get(
        f"{API}/tickets", params={"status": payload}, headers=auth(tokens["admin"])
    )
    assert_no_server_error(response, f"status={payload!r}")
    if response.status_code == 200:
        assert response.json() == [], "a bogus status filter matched rows"
    assert_tables_intact(db)


@pytest.mark.parametrize("payload", PAYLOADS[:6])
def test_ticket_body_fields_are_data_not_sql(client, db, tokens, payload):
    response = client.post(
        f"{API}/tickets",
        json={"subject": payload, "description": payload, "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_no_server_error(response, f"ticket subject={payload!r}")
    assert_tables_intact(db)
    if response.status_code == 201:
        # Stored verbatim: escaping belongs at the boundary that renders it.
        assert response.json()["subject"] == payload


@pytest.mark.parametrize("payload", PAYLOADS[:6])
def test_tag_name_is_data_not_sql(client, db, tokens, payload):
    response = client.post(f"{API}/tags", json={"name": payload}, headers=auth(tokens["agent"]))
    assert response.status_code in (201, 409), response.text
    assert_tables_intact(db)


def test_injection_cannot_escalate_a_role(client, db, tokens, user_ids):
    """The nastiest payload: an UPDATE that would make everyone an admin.

    Compares an admin count before and after rather than asserting an absolute
    number — other tests legitimately create admin accounts, and a test that
    depends on the total would be measuring the wrong thing.
    """
    where = "r.name = 'admin'"
    joined = "users u JOIN roles r ON r.id = u.role_id"
    before = count_where(db, joined, where, {})

    payload = "'; UPDATE users SET role_id = (SELECT id FROM roles WHERE name='admin'); --"
    client.get(f"{API}/search/tickets", params={"q": payload}, headers=auth(tokens["admin"]))
    client.post(
        f"{API}/tickets",
        json={"subject": payload, "description": payload, "channel": "portal"},
        headers=auth(tokens["requester"]),
    )

    after = count_where(db, joined, where, {})
    assert after == before, f"the injection changed the admin count from {before} to {after}"

    still_a_requester = client.get(f"{API}/users", headers=auth(tokens["requester"]))
    assert_status(still_a_requester, 403, "requester gained admin rights")


def test_injection_in_a_uuid_path_parameter_is_rejected_by_the_router(client, tokens):
    """UUID-typed path params never reach SQL — FastAPI rejects them at 422."""
    for payload in ["' OR 1=1 --", "1;DROP TABLE tickets", "../../etc/passwd"]:
        response = client.get(f"{API}/tickets/{payload}", headers=auth(tokens["admin"]))
        assert response.status_code in (404, 422), f"{payload}: {response.status_code}"


def test_injection_in_saved_view_filters_is_stored_as_json(client, db, tokens):
    """`filters` is opaque JSONB — it must never be interpolated into a query."""
    view = client.post(
        f"{API}/saved-views",
        json={"name": f.rand("sqli-"), "filters": {"status": "'; DROP TABLE tickets; --"}},
        headers=auth(tokens["requester"]),
    )
    assert_status(view, 201)
    assert_tables_intact(db)
    client.delete(f"{API}/saved-views/{view.json()['id']}", headers=auth(tokens["requester"]))


def test_automation_condition_values_are_data_not_sql(client, db, tokens):
    rule = f.make_rule(
        client,
        tokens["admin"],
        conditions=[{"field": "subject", "op": "contains", "value": "'; DROP TABLE tickets; --"}],
        actions=[],
    )
    f.make_ticket(client, tokens["requester"])
    assert_tables_intact(db)
    f.delete_rule(client, tokens["admin"], rule["id"])
