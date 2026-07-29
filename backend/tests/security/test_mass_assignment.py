"""Mass assignment: fields the client is not supposed to control.

Pydantic ignores unknown keys by default, so the risk is not the unknown ones —
it is the *known* server-owned columns that a request body might reach through a
model that is too permissive. Each test asserts on the persisted row, because a
response body can look right while the database took the value.
"""

import uuid

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_forbidden, assert_status
from tests.helpers.auth import API, auth

FORGED = uuid.UUID(int=0)


def _row(db, table: str, row_id: str) -> dict:
    with db.connect() as conn:
        return dict(
            conn.execute(sa.text(f"SELECT * FROM {table} WHERE id = :i"), {"i": row_id})
            .mappings()
            .one()
        )


def test_ticket_creation_ignores_server_owned_columns(client, db, tokens, user_ids):
    response = client.post(
        f"{API}/tickets",
        json={
            "subject": f"mass assignment {f.rand()}",
            "description": "d",
            "channel": "portal",
            # None of these belong to the caller:
            "status": "closed",
            "requester_id": user_ids["admin"],
            "assignee_id": user_ids["agent"],
            "queue_id": str(FORGED),
            "priority_id": str(FORGED),
            "reopened_count": 99,
            "display_id": 424242,
            "resolved_at": "2020-01-01T00:00:00Z",
            "closed_at": "2020-01-01T00:00:00Z",
            "merged_into_ticket_id": str(FORGED),
            "id": str(FORGED),
        },
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)
    ticket = _row(db, "tickets", response.json()["id"])

    assert ticket["status"] == "new", "client set the initial status"
    assert str(ticket["requester_id"]) == user_ids["requester"], "client spoofed the requester"
    assert ticket["assignee_id"] is None, "client self-assigned at creation"
    assert ticket["queue_id"] is None and ticket["priority_id"] is None
    assert ticket["reopened_count"] == 0
    assert ticket["display_id"] != 424242, "client chose its own display_id"
    assert ticket["resolved_at"] is None and ticket["closed_at"] is None
    assert ticket["merged_into_ticket_id"] is None
    assert str(ticket["id"]) != str(FORGED), "client chose its own primary key"


def test_ticket_patch_cannot_reach_status_or_assignee(client, db, tokens, user_ids):
    ticket = f.make_ticket(client, tokens["requester"])
    response = client.patch(
        f"{API}/tickets/{ticket['id']}",
        json={
            "subject": "legit edit",
            "status": "closed",
            "assignee_id": user_ids["agent"],
            "requester_id": user_ids["admin"],
            "reopened_count": 50,
        },
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 200)
    row = _row(db, "tickets", ticket["id"])
    assert row["subject"] == "legit edit"
    assert row["status"] == "new", "status changed through PATCH /tickets"
    assert row["assignee_id"] is None, "assignee changed through PATCH /tickets"
    assert str(row["requester_id"]) == user_ids["requester"]
    assert row["reopened_count"] == 0


@pytest.mark.parametrize(
    "body,label",
    [
        ({"role": "admin"}, "role"),
        ({"is_active": False}, "is_active"),
        ({"team_id": None}, "team_id"),
    ],
)
def test_a_user_cannot_grant_themselves_admin_fields(client, tokens, user_ids, body, label):
    response = client.patch(
        f"{API}/users/{user_ids['requester']}", json=body, headers=auth(tokens["requester"])
    )
    assert_forbidden(response, f"requester set their own {label}")


def test_self_service_profile_edits_ignore_privileged_keys(client, db, tokens, user_ids):
    """A legal self-edit that smuggles admin fields must be rejected outright,
    not partially applied."""
    response = client.patch(
        f"{API}/users/{user_ids['requester']}",
        json={"full_name": "New Name", "role": "admin"},
        headers=auth(tokens["requester"]),
    )
    assert_forbidden(response, "mixed self-edit + privilege escalation")

    row = _row(db, "users", user_ids["requester"])
    with db.connect() as conn:
        role = conn.execute(
            sa.text("SELECT name FROM roles WHERE id = :i"), {"i": row["role_id"]}
        ).scalar()
    assert role == "requester"
    assert row["full_name"] != "New Name", "the rejected request was still partly applied"


def test_registration_cannot_choose_its_own_role(client, db):
    """Self-registration is always a requester (App Flow §4)."""
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f.unique_email("selfadmin"),
            "password": "Password123!",
            "full_name": "Wants Admin",
            "role": "admin",
            "is_active": True,
            "email_verified_at": "2020-01-01T00:00:00Z",
        },
    )
    assert_status(response, 201)
    assert response.json()["role"] == "requester", "registration honoured a client-chosen role"
    assert response.json()["email_verified"] is False, "client self-verified their email"


def test_password_hash_can_never_be_supplied_directly(client, db):
    """A caller-supplied hash would let an attacker set a known credential."""
    email = f.unique_email("hash")
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "full_name": "H",
            "password_hash": "$2b$12$" + "A" * 53,
        },
    )
    assert_status(response, 201)
    with db.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT password_hash FROM users WHERE email = :e"), {"e": email}
        ).scalar_one()
    assert stored != "$2b$12$" + "A" * 53, "client-supplied password_hash was stored"

    from app.auth import security

    assert security.verify_password("Password123!", stored)


def test_comment_cannot_be_flagged_as_ai_generated_by_the_client(client, db, tokens):
    """`is_ai_generated` drives the AI-performance report; only the AI writes it."""
    ticket = f.make_ticket(client, tokens["requester"])
    response = client.post(
        f"{API}/tickets/{ticket['id']}/comments",
        json={
            "body": "not really from the model",
            "is_ai_generated": True,
            "ai_confidence": 99.9,
            "author_id": None,
        },
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)
    row = _row(db, "comments", response.json()["id"])
    assert row["is_ai_generated"] is False, "client marked its own comment AI-generated"
    assert row["ai_confidence"] is None
    assert row["author_id"] is not None, "client anonymised its own comment"


def test_automation_rule_cannot_forge_its_creator(client, db, tokens, user_ids):
    rule = f.make_rule(client, tokens["admin"], created_by=user_ids["requester"])
    row = _row(db, "automation_rules", rule["id"])
    assert str(row["created_by"]) == user_ids["admin"], "rule recorded a forged author"
    f.delete_rule(client, tokens["admin"], rule["id"])


def test_saved_view_cannot_be_created_on_behalf_of_another_user(client, db, tokens, user_ids):
    response = client.post(
        f"{API}/saved-views",
        json={"name": f.rand("mass-"), "filters": {}, "user_id": user_ids["admin"]},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 201)
    row = _row(db, "saved_views", response.json()["id"])
    assert str(row["user_id"]) == user_ids["requester"], "saved view was planted on another user"
    client.delete(f"{API}/saved-views/{response.json()['id']}", headers=auth(tokens["requester"]))


def test_webhook_secret_is_never_echoed_on_read(client, tokens):
    """The plaintext secret is shown once at creation and never again."""
    created = client.post(
        f"{API}/webhooks",
        json={"event_type": "ticket_created", "target_url": "https://example.com/hook"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)
    assert "secret" in created.json(), "creation must return the secret once"

    listed = client.get(f"{API}/webhooks", headers=auth(tokens["admin"]))
    entry = next(w for w in listed.json() if w["id"] == created.json()["id"])
    assert "secret" not in entry, "webhook secret echoed on read"

    client.delete(f"{API}/webhooks/{created.json()['id']}", headers=auth(tokens["admin"]))
