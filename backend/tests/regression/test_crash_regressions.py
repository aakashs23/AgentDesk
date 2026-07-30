"""Inputs that make the API return 500 instead of a 4xx.

Every one of these is reachable by any authenticated caller — several by an
anonymous one — with a single small request. That makes them availability bugs
as much as correctness bugs: a client that sends them gets no actionable error,
and the server logs a full stack trace per attempt.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_no_server_error
from tests.helpers.auth import API, auth

# --- BUG-1: passwords over bcrypt's 72-byte limit ---


def test_registering_with_a_long_password_returns_a_validation_error(client):
    """BUG-1 (High): a password over 72 bytes crashes registration.

    Root cause: `app/auth/security.hash_password` hands the raw password to
    `bcrypt.hashpw`, which raises `ValueError: password cannot be longer than
    72 bytes` on bcrypt >= 4.1. Nothing catches it, so it surfaces as a 500.

    Reachable unauthenticated, at `POST /api/v1/auth/register`.

    Fix: bound the field where it is declared — add `max_length=72` to
    `RegisterRequest.password` and `PasswordResetConfirm.new_password` in
    `app/auth/schemas.py`, so the rejection is a 422 from the schema rather than
    an exception from the hasher.
    """
    response = client.post(
        f"{API}/auth/register",
        json={"email": f.unique_email("longpw"), "password": "a" * 200, "full_name": "N"},
    )
    assert_no_server_error(response, "200-character password")
    assert response.status_code == 422


def test_resetting_to_a_long_password_returns_a_validation_error(client, db, outbox):
    """BUG-1, second entry point: the same crash on the password-reset path."""
    from tests.helpers.auth import link_token_from_outbox

    user = f.verified_requester(client, db)
    client.post(f"{API}/auth/password-reset/request", json={"email": user["email"]})
    raw = link_token_from_outbox(outbox, user["email"], "Reset")

    response = client.post(
        f"{API}/auth/password-reset/confirm", json={"token": raw, "new_password": "b" * 100}
    )
    assert_no_server_error(response, "100-character new password")
    assert response.status_code == 422


# --- BUG-2: NUL bytes in any text column ---


@pytest.mark.parametrize("field", ["subject", "description"], ids=["subject", "description"])
def test_a_nul_byte_in_a_ticket_field_is_rejected_not_crashed(client, tokens, field):
    """BUG-2 (High): `\\x00` anywhere in a text field returns 500.

    Root cause: PostgreSQL text columns cannot store U+0000; asyncpg raises on
    the INSERT. Pydantic's `str` accepts it, so nothing rejects it earlier and
    the driver error escapes as an unhandled 500.

    Any authenticated caller can trigger it with one request, and it fires on
    ticket subject/description, comment bodies, tag names, and the search query.

    Fix: strip or reject NUL at the boundary. The smallest version is one
    reusable annotated type in `app/tickets/schemas.py` —
    `AfterValidator(lambda s: s.replace("\\x00", ""))` — applied to the free-text
    fields, so it is handled once rather than at every call site.
    """
    body = {"subject": "safe", "description": "safe", "channel": "portal"}
    body[field] = "before\x00after"
    response = client.post(f"{API}/tickets", json=body, headers=auth(tokens["requester"]))
    assert_no_server_error(response, f"NUL byte in {field}")


def test_a_nul_byte_in_a_comment_is_rejected_not_crashed(client, tokens):
    """BUG-2, second entry point: comment bodies."""
    ticket = f.make_ticket(client, tokens["requester"])
    response = f.comment(client, tokens["requester"], ticket["id"], "hello\x00world")
    assert_no_server_error(response, "NUL byte in a comment body")


def test_a_nul_byte_in_a_tag_name_is_rejected_not_crashed(client, tokens):
    """BUG-2, third entry point: tag names."""
    response = client.post(
        f"{API}/tags", json={"name": f"tag\x00{f.rand()}"}, headers=auth(tokens["agent"])
    )
    assert_no_server_error(response, "NUL byte in a tag name")


def test_a_nul_byte_in_a_search_query_is_rejected_not_crashed(client, tokens):
    """BUG-2, fourth entry point: the search query parameter."""
    response = client.get(
        f"{API}/search/tickets", params={"q": "hello\x00world"}, headers=auth(tokens["admin"])
    )
    assert_no_server_error(response, "NUL byte in a search query")


# --- BUG-3: unbounded JSON nesting ---


def test_a_deeply_nested_json_body_is_rejected_not_crashed(client, db, tokens):
    """BUG-3 (Medium): deeply nested JSON in a free-form field returns 500.

    Root cause: `SavedViewIn.filters` and `UserUpdate.notification_preferences`
    are untyped `dict`, so arbitrary nesting is accepted, then Python's
    recursive serializer blows its stack on the way back out.

    Fix: cap nesting where the value enters — a small `AfterValidator` on
    `filters` that walks the structure and rejects beyond a fixed depth
    (8 is generous for a filter set).

    Uses a throwaway account on purpose: the write commits before it fails, and
    a poisoned row would permanently break saved-view listing for whichever user
    owns it (see the next test). Doing that to a shared fixture account would
    break unrelated tests.
    """
    owner = f.verified_requester(client, db)
    deep = current = {}
    for _ in range(2000):
        current["a"] = {}
        current = current["a"]

    response = client.post(
        f"{API}/saved-views",
        json={"name": f.rand("deep-"), "filters": deep},
        headers=auth(owner["token"]),
    )
    assert_no_server_error(response, "2000-deep JSON")


def test_a_stored_deep_filter_does_not_break_the_saved_view_list(client, db, tokens):
    """BUG-3b (High): nesting accepted on write permanently breaks the read.

    This is the damaging half of BUG-3, and it is worse than a crash. At depth
    ~300 the row **commits**, and only then does serializing the response blow
    up — so the caller sees a 500 while the write has already landed. From that
    point `GET /saved-views` returns 500 for that user forever, for *every* view
    they own, not just the poisoned one. No API can remove it, because listing
    is the thing that crashes and DELETE needs the id the list would have shown.
    Recovery requires direct database access.

    Self-inflicted per user, so not a cross-tenant denial of service — but it is
    a permanent, unrecoverable break of a feature from one ordinary request.

    Fix: the same depth cap as BUG-3, enforced on write. Validating only on read
    would leave already-stored rows poisoned.
    """
    owner = f.verified_requester(client, db)
    deep = current = {}
    for _ in range(300):
        current["a"] = {}
        current = current["a"]

    client.post(
        f"{API}/saved-views",
        json={"name": f.rand("deep-"), "filters": deep},
        headers=auth(owner["token"]),
    )
    listed = client.get(f"{API}/saved-views", headers=auth(owner["token"]))
    assert_no_server_error(listed, "listing saved views after a deep filter was stored")
