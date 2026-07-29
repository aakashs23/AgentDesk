"""Input validation at the trust boundary.

Everything here is about the *shape* of a request: wrong types, wrong
vocabulary, absent required fields, and structural abuse (oversize bodies,
unexpected containers). The rule under test is that the API rejects with a 4xx
and a useful message — never a 500, and never by quietly coercing the value.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import (
    assert_no_server_error,
    assert_status,
    assert_validation_error,
)
from tests.helpers.auth import API, auth

TICKET = f"{API}/tickets"


# --- Required fields and types ---


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"subject": "only subject"},
        {"description": "only description"},
        {"subject": "", "description": "d"},
        {"subject": "s", "description": ""},
        {"subject": None, "description": "d"},
        {"subject": 12345, "description": "d"},
        {"subject": ["a", "b"], "description": "d"},
        {"subject": {"nested": "object"}, "description": "d"},
        {"subject": True, "description": "d"},
    ],
)
def test_malformed_ticket_bodies_are_rejected(client, tokens, body):
    response = client.post(TICKET, json=body, headers=auth(tokens["requester"]))
    assert_validation_error(response, f"body={body}")


@pytest.mark.parametrize("channel", ["", "carrier-pigeon", "PORTAL", "portal ", "../portal"])
def test_unknown_ticket_channel_is_rejected(client, tokens, channel):
    response = client.post(
        TICKET,
        json={"subject": "s", "description": "d", "channel": channel},
        headers=auth(tokens["requester"]),
    )
    assert_validation_error(response, f"channel={channel!r}")


@pytest.mark.parametrize(
    "email",
    ["", "not-an-email", "@example.com", "a@", "a@b", "a b@example.com", "a@@example.com"],
)
def test_invalid_emails_are_rejected_at_registration(client, email):
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "Password123!", "full_name": "N"},
    )
    assert_validation_error(response, f"email={email!r}")


@pytest.mark.parametrize("password", ["", "short", "1234567"])
def test_passwords_below_the_minimum_length_are_rejected(client, password):
    response = client.post(
        f"{API}/auth/register",
        json={"email": f.unique_email(), "password": password, "full_name": "N"},
    )
    assert_validation_error(response, f"password len={len(password)}")


def test_duplicate_registration_is_a_conflict_not_a_crash(client):
    created = f.register_requester(client)
    again = client.post(
        f"{API}/auth/register",
        json={
            "email": created["email"],
            "password": created["password"],
            "full_name": created["full_name"],
        },
    )
    assert_status(again, 409, "duplicate email")


@pytest.mark.parametrize("role", ["", "superadmin", "ADMIN", "root", "requester "])
def test_inviting_a_user_with_an_unknown_role_is_rejected(client, tokens, role):
    response = f.invite_user(client, tokens["admin"], role)
    assert_validation_error(response, f"role={role!r}")


def test_inviting_a_user_into_an_unknown_team_is_rejected(client, tokens):
    response = f.invite_user(
        client, tokens["admin"], "agent", team_id="00000000-0000-0000-0000-000000000000"
    )
    assert_validation_error(response, "unknown team")


# --- Unknown vocabulary in domain enums ---


@pytest.mark.parametrize("status", ["hacked", "", "NEW", "deleted", "1"])
def test_unknown_ticket_status_is_rejected(client, db, tokens, status):
    catalog = f.catalog(db)
    ticket = f.make_ticket(client, tokens["requester"])
    f.assign(client, tokens["admin"], ticket["id"], queue_id=catalog["queue_id"])
    response = f.set_status(client, tokens["agent"], ticket["id"], status)
    assert response.status_code in (409, 422), f"status={status!r}: {response.status_code}"


@pytest.mark.parametrize("trigger", ["", "on_tuesday", "TICKET_CREATED", "ticket_deleted"])
def test_unknown_automation_trigger_is_rejected(client, tokens, trigger):
    response = client.post(
        f"{API}/admin/automation-rules",
        json={"name": f.rand(), "trigger_type": trigger, "conditions": [], "actions": []},
        headers=auth(tokens["admin"]),
    )
    assert_validation_error(response, f"trigger={trigger!r}")


@pytest.mark.parametrize("field", ["password_hash", "is_admin", "'; DROP", ""])
def test_unknown_automation_condition_field_is_rejected(client, tokens, field):
    response = client.post(
        f"{API}/admin/automation-rules",
        json={
            "name": f.rand(),
            "trigger_type": "ticket_created",
            "conditions": [{"field": field, "op": "eq", "value": "x"}],
            "actions": [],
        },
        headers=auth(tokens["admin"]),
    )
    assert_validation_error(response, f"condition field={field!r}")


@pytest.mark.parametrize("event", ["", "ticket_deleted", "user_created"])
def test_unknown_webhook_event_is_rejected(client, tokens, event):
    response = client.post(
        f"{API}/webhooks",
        json={"event_type": event, "target_url": "https://example.com/x"},
        headers=auth(tokens["admin"]),
    )
    assert_validation_error(response, f"event={event!r}")


@pytest.mark.parametrize("trigger", ["", "nope", "ticket_created"])
def test_unknown_notification_preference_trigger_is_rejected(client, tokens, trigger):
    """`ticket_created` is an automation trigger, not a notification one."""
    response = client.patch(
        f"{API}/notifications/preferences",
        json={"preferences": {trigger: {"email": False}}},
        headers=auth(tokens["requester"]),
    )
    assert_validation_error(response, f"trigger={trigger!r}")


def test_unknown_notification_channel_is_rejected(client, tokens):
    response = client.patch(
        f"{API}/notifications/preferences",
        json={"preferences": {"sla_warning": {"carrier_pigeon": False}}},
        headers=auth(tokens["requester"]),
    )
    assert_validation_error(response, "unknown channel")


@pytest.mark.parametrize("report_type", ["", "everything", "agent_productivity_v2"])
def test_unknown_report_type_is_rejected(client, tokens, report_type):
    response = client.post(
        f"{API}/reports/generate",
        json={"report_type": report_type},
        headers=auth(tokens["agent"]),
    )
    assert_validation_error(response, f"report_type={report_type!r}")


@pytest.mark.parametrize("fmt", ["exe", "docx", "", "../etc/passwd"])
def test_unknown_export_format_is_rejected(client, tokens, fmt):
    created = client.post(
        f"{API}/reports/generate",
        json={"report_type": "ticket_trends"},
        headers=auth(tokens["agent"]),
    )
    response = client.get(
        f"{API}/reports/{created.json()['id']}/export",
        params={"format": fmt},
        headers=auth(tokens["agent"]),
    )
    assert_validation_error(response, f"format={fmt!r}")


# --- Pagination bounds ---


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 101},
        {"limit": 10**9},
        {"limit": "abc"},
        {"offset": -1},
        {"offset": "abc"},
    ],
)
def test_out_of_range_pagination_is_rejected(client, tokens, params):
    response = client.get(TICKET, params=params, headers=auth(tokens["admin"]))
    assert_validation_error(response, f"params={params}")


@pytest.mark.parametrize("params", [{"limit": 1}, {"limit": 100}, {"offset": 0}, {"offset": 10**6}])
def test_in_range_pagination_is_accepted(client, tokens, params):
    response = client.get(TICKET, params=params, headers=auth(tokens["admin"]))
    assert_status(response, 200, f"params={params}")


def test_search_requires_a_non_empty_query(client, tokens):
    assert_validation_error(
        client.get(f"{API}/search/tickets", params={"q": ""}, headers=auth(tokens["admin"]))
    )
    assert_validation_error(client.get(f"{API}/search/tickets", headers=auth(tokens["admin"])))


# --- Malformed request envelopes ---


def test_invalid_json_body_is_rejected(client, tokens):
    response = client.post(
        TICKET,
        content=b"{not valid json",
        headers={**auth(tokens["requester"]), "Content-Type": "application/json"},
    )
    assert_no_server_error(response, "malformed JSON")
    assert response.status_code == 422


def test_a_json_array_where_an_object_is_expected_is_rejected(client, tokens):
    response = client.post(
        TICKET, json=["subject", "description"], headers=auth(tokens["requester"])
    )
    assert_validation_error(response, "array body")


def test_a_bare_scalar_body_is_rejected(client, tokens):
    for body in ["just a string", 42, True, None]:
        response = client.post(TICKET, json=body, headers=auth(tokens["requester"]))
        assert_validation_error(response, f"scalar body {body!r}")


def test_wrong_content_type_is_rejected(client, tokens):
    response = client.post(
        TICKET,
        content=b"subject=s&description=d",
        headers={**auth(tokens["requester"]), "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert_no_server_error(response, "form body on a JSON endpoint")
    assert response.status_code == 422


def test_malformed_uuid_path_parameters_are_rejected(client, tokens):
    for bad in ["abc", "123", "not-a-uuid", "00000000-0000-0000-0000-00000000000"]:
        response = client.get(f"{API}/tickets/{bad}", headers=auth(tokens["admin"]))
        assert_validation_error(response, f"uuid={bad!r}")


def test_unknown_routes_return_a_clean_404(client, tokens):
    # No `..` case here — httpx normalises it away before it leaves the client.
    # Traversal is exercised where it actually reaches the filesystem, in
    # tests/security/test_file_uploads.py.
    for path in ["/nope", "/api/v1/nope", "/api/v2/tickets", "/api/v1/tickets/x/y/z"]:
        response = client.get(path, headers=auth(tokens["admin"]))
        assert response.status_code == 404, f"{path}: {response.status_code}"
        assert_no_server_error(response, path)


def test_wrong_method_returns_405_not_500(client, tokens):
    for method, path in [("DELETE", "/api/v1/tickets"), ("PUT", "/api/v1/auth/login")]:
        response = client.request(method, path, headers=auth(tokens["admin"]))
        assert response.status_code in (404, 405), f"{method} {path}: {response.status_code}"


# --- Structural abuse ---


def test_an_unexpected_array_in_a_dict_field_is_rejected(client, tokens):
    response = client.patch(
        f"{API}/notifications/preferences",
        json={"preferences": {"sla_warning": ["email", "in_app"]}},
        headers=auth(tokens["requester"]),
    )
    assert_validation_error(response, "array where a channel map was expected")


def test_a_non_boolean_channel_flag_is_rejected(client, tokens):
    response = client.patch(
        f"{API}/notifications/preferences",
        json={"preferences": {"sla_warning": {"email": "maybe"}}},
        headers=auth(tokens["requester"]),
    )
    assert_validation_error(response, "non-boolean channel flag")


def test_extra_unknown_keys_are_ignored_rather_than_rejected(client, tokens):
    """FastAPI's default: unknown keys are dropped. Documented so a future
    `extra='forbid'` change is a deliberate decision, not a surprise."""
    response = client.post(
        TICKET,
        json={
            "subject": f"extras {f.rand()}",
            "description": "d",
            "channel": "portal",
            "totally_unknown_field": "ignored",
        },
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)
    assert "totally_unknown_field" not in response.json()
