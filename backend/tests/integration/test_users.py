"""User management (TRD §3 Users; permissions per Doc 05 §7).

The invite → set-password → login lifecycle, the admin-only mutations, and the
filtering the directory supports.
"""

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.assertions import assert_never_leaks_secrets, assert_status
from tests.helpers.auth import API, ROLES, auth, link_token_from_outbox, login

# --- Invite lifecycle ---


@pytest.mark.parametrize("role", ROLES)
def test_an_admin_can_invite_a_user_of_any_role(client, db, tokens, role):
    # A throwaway team, not the seeded one: adding a second team_lead there
    # makes every escalation test in the suite pick an arbitrary lead.
    team_id = None if role == "requester" else f.make_team(db)
    response = f.invite_user(client, tokens["admin"], role, team_id=team_id)
    assert_status(response, 201, f"invite {role}")

    created = response.json()
    assert created["role"] == role
    assert created["is_active"] is True
    assert created["email_verified"] is False, "an invited user starts unverified"
    assert_never_leaks_secrets(created)


def test_an_invited_user_activates_by_setting_a_password(client, tokens, outbox):
    """The invite link is a password-reset token; following it also verifies the
    address, since receiving the mail proves ownership."""
    response = f.invite_user(client, tokens["admin"], "agent")
    assert_status(response, 201)
    invited = response.json()

    # The account cannot be used before the invite is accepted.
    assert_status(login(client, invited["email"], "Password123!"), 401)

    token = link_token_from_outbox(outbox, invited["email"], "invited")
    assert_status(
        client.post(
            f"{API}/auth/password-reset/confirm",
            json={"token": token, "new_password": "ChosenPassword1!"},
        ),
        200,
    )

    logged_in = login(client, invited["email"], "ChosenPassword1!")
    assert_status(logged_in, 200, "invited user could not log in after activating")
    assert logged_in.json()["user"]["role"] == "agent"
    assert logged_in.json()["user"]["email_verified"] is True


def test_inviting_an_existing_address_is_a_conflict(client, tokens):
    first = f.invite_user(client, tokens["admin"], "agent")
    assert_status(first, 201)
    again = client.post(
        f"{API}/users",
        json={"email": first.json()["email"], "full_name": "Dup", "role": "agent"},
        headers=auth(tokens["admin"]),
    )
    assert_status(again, 409, "duplicate invite")


# --- Reads ---


def test_the_directory_never_exposes_credentials(client, tokens):
    response = client.get(f"{API}/users", headers=auth(tokens["admin"]))
    assert_status(response, 200)
    assert response.json(), "the seeded directory should not be empty"
    for user in response.json():
        assert_never_leaks_secrets(user)
        assert set(user) == {
            "id",
            "email",
            "full_name",
            "role",
            "team_id",
            "is_active",
            "email_verified",
            "theme_preference",
        }, f"unexpected field set: {sorted(user)}"


@pytest.mark.parametrize("role", ROLES)
def test_the_directory_can_be_filtered_by_role(client, tokens, role):
    response = client.get(f"{API}/users", params={"role": role}, headers=auth(tokens["admin"]))
    assert_status(response, 200, f"role={role}")
    assert response.json(), f"no users returned for role={role}"
    assert {u["role"] for u in response.json()} == {role}


def test_filtering_by_an_unknown_role_is_rejected(client, tokens):
    response = client.get(
        f"{API}/users", params={"role": "sorcerer"}, headers=auth(tokens["admin"])
    )
    assert_status(response, 422, "unknown role filter")


def test_the_directory_can_be_filtered_by_team(client, db, tokens):
    catalog = f.catalog(db)
    response = client.get(
        f"{API}/users", params={"team_id": catalog["team_id"]}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert response.json()
    assert {u["team_id"] for u in response.json()} == {catalog["team_id"]}


def test_the_directory_is_ordered_deterministically(client, tokens):
    """Ordered by created_at, so two calls agree — pagination would be unusable
    otherwise (and there is none yet, which the API surface test records)."""
    first = client.get(f"{API}/users", headers=auth(tokens["admin"])).json()
    second = client.get(f"{API}/users", headers=auth(tokens["admin"])).json()
    assert [u["id"] for u in first] == [u["id"] for u in second]


# --- Updates ---


def test_a_user_can_edit_their_own_profile_fields(client, db, tokens, user_ids):
    user = f.verified_requester(client, db)
    response = client.patch(
        f"{API}/users/{user['user']['id']}",
        json={"full_name": "Renamed Person", "theme_preference": "dark"},
        headers=auth(user["token"]),
    )
    assert_status(response, 200)
    assert response.json()["full_name"] == "Renamed Person"
    assert response.json()["theme_preference"] == "dark"


def test_an_admin_can_change_a_users_role(client, db, tokens):
    user = f.activated_user(client, db, tokens["admin"], "agent")
    response = client.patch(
        f"{API}/users/{user['id']}", json={"role": "team_lead"}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert response.json()["role"] == "team_lead"


def test_a_role_change_takes_effect_on_the_next_request(client, db, tokens):
    """The JWT still carries the old role; authorization reads the row instead.

    Probed with status-history, which is Team Lead+ (Doc 05 §6). `GET /users`
    used to be the probe here, but Phase 11 opened it to agents for the Agent
    Console's assignment and @mention lookups, so it no longer separates the two
    roles.
    """
    user = f.activated_user(client, db, tokens["admin"], "agent", team_id=f.make_team(db))
    ticket = f.make_ticket(client, tokens["requester"])
    # Assigned to them, so the row is inside their scope before *and* after the
    # promotion — otherwise the second call would 404 on row scope and say
    # nothing about the role gate this test is actually about.
    assert_status(
        client.post(
            f"{API}/tickets/{ticket['id']}/assign",
            json={"assignee_id": user["id"]},
            headers=auth(tokens["admin"]),
        ),
        200,
    )
    history = f"{API}/tickets/{ticket['id']}/status-history"
    assert_status(client.get(history, headers=auth(user["token"])), 403)

    assert_status(
        client.patch(
            f"{API}/users/{user['id']}", json={"role": "team_lead"}, headers=auth(tokens["admin"])
        ),
        200,
    )
    assert_status(
        client.get(history, headers=auth(user["token"])),
        200,
        "the promoted user still had the old role on their existing token",
    )


def test_updating_to_an_unknown_role_is_rejected(client, db, tokens):
    user = f.activated_user(client, db, tokens["admin"], "agent")
    response = client.patch(
        f"{API}/users/{user['id']}", json={"role": "wizard"}, headers=auth(tokens["admin"])
    )
    assert_status(response, 422, "unknown role")


def test_updating_to_an_unknown_team_is_rejected(client, db, tokens):
    user = f.activated_user(client, db, tokens["admin"], "agent")
    response = client.patch(
        f"{API}/users/{user['id']}",
        json={"team_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth(tokens["admin"]),
    )
    assert_status(response, 422, "unknown team")


def test_updating_an_unknown_user_is_a_404(client, tokens):
    response = client.patch(
        f"{API}/users/00000000-0000-0000-0000-000000000000",
        json={"full_name": "Ghost"},
        headers=auth(tokens["admin"]),
    )
    assert_status(response, 404)


# --- Deactivation ---


def test_deactivation_is_soft_and_revokes_sessions(client, db, tokens):
    """Doc 05 keeps the row for referential integrity; DELETE means deactivate."""
    user = f.activated_user(client, db, tokens["admin"], "agent")
    refresh = login(client, user["email"], user["password"]).json()["refresh_token"]

    assert_status(client.delete(f"{API}/users/{user['id']}", headers=auth(tokens["admin"])), 204)

    with db.connect() as conn:
        row = conn.execute(
            sa.text("SELECT is_active FROM users WHERE id = :i"), {"i": user["id"]}
        ).one_or_none()
    assert row is not None, "the user row was hard-deleted"
    assert row[0] is False

    assert_status(client.post(f"{API}/auth/refresh", json={"refresh_token": refresh}), 401)
    assert_status(login(client, user["email"], user["password"]), 403, "deactivated login")


def test_deactivating_an_already_inactive_user_is_idempotent(client, db, tokens):
    user = f.activated_user(client, db, tokens["admin"], "agent")
    for _ in range(2):
        assert_status(
            client.delete(f"{API}/users/{user['id']}", headers=auth(tokens["admin"])), 204
        )


def test_deactivating_an_unknown_user_is_a_404(client, tokens):
    response = client.delete(
        f"{API}/users/00000000-0000-0000-0000-000000000000", headers=auth(tokens["admin"])
    )
    assert_status(response, 404)


def test_an_admin_can_reactivate_a_user(client, db, tokens):
    user = f.activated_user(client, db, tokens["admin"], "agent")
    assert_status(client.delete(f"{API}/users/{user['id']}", headers=auth(tokens["admin"])), 204)

    response = client.patch(
        f"{API}/users/{user['id']}", json={"is_active": True}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert response.json()["is_active"] is True
    assert_status(login(client, user["email"], user["password"]), 200, "reactivated login")
