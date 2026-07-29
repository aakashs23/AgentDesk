"""Phase 3 checkpoint: login for all roles, token rotation/revocation, reset +
verification flows, invite flow, RBAC enforcement (incl. Acceptance Criteria AC3).

Runs against the migrated + seeded database.
"""

import re
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.auth.deps import scope_tickets_to_caller
from app.notifications import mailer

SEED_PASSWORD = "Password123!"
SEED_USERS = {
    "requester": "requester@agentdesk.dev",
    "agent": "agent@agentdesk.dev",
    "team_lead": "lead@agentdesk.dev",
    "admin": "admin@agentdesk.dev",
}
API = "/api/v1"


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(
        mailer, "send_email", lambda to, subject, body: sent.append({"to": to, "body": body})
    )
    return sent


def _token_from(email_body: str) -> str:
    return re.search(r"token=([A-Za-z0-9_\-]+)", email_body).group(1)


def _login(client, email, password=SEED_PASSWORD):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _unique_email() -> str:
    return f"test-{uuid.uuid4().hex[:10]}@agentdesk.dev"


# --- Checkpoint: all four roles can log in ---


def test_all_seeded_roles_can_log_in(client):
    for role, email in SEED_USERS.items():
        response = _login(client, email)
        assert response.status_code == 200, (role, response.text)
        body = response.json()
        assert body["user"]["role"] == role
        assert body["access_token"] and body["refresh_token"]
        assert "password_hash" not in response.text


def test_login_wrong_password_rejected(client):
    assert _login(client, SEED_USERS["admin"], "wrong-password").status_code == 401


# --- Checkpoint: refresh rotation and revocation; logout invalidates ---


def test_refresh_rotation_single_use(client):
    tokens = _login(client, SEED_USERS["agent"]).json()
    first = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200
    # Rotated: the old refresh token is now revoked, the new one works
    replay = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    second = client.post(
        f"{API}/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
    )
    assert second.status_code == 200


def test_logout_revokes_refresh_token(client):
    tokens = _login(client, SEED_USERS["agent"]).json()
    response = client.post(
        f"{API}/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=_auth(tokens["access_token"]),
    )
    assert response.status_code == 204
    after = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert after.status_code == 401


# --- Checkpoint: registration + email verification end-to-end ---


def test_register_verify_login_flow(client, outbox):
    email = _unique_email()
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "NewUserPass1!", "full_name": "New Requester"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "requester"
    # Unverified accounts cannot log in yet (App Flow Doc 03 §4)
    assert _login(client, email, "NewUserPass1!").status_code == 403
    token = _token_from(outbox[-1]["body"])
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 200
    assert _login(client, email, "NewUserPass1!").status_code == 200
    # Verification tokens are single-use
    assert client.post(f"{API}/auth/verify-email", json={"token": token}).status_code == 400


# --- Checkpoint: password reset end-to-end ---


def test_password_reset_flow(client, outbox):
    email = _unique_email()
    client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "OriginalPass1!", "full_name": "Reset Me"},
    )
    client.post(f"{API}/auth/verify-email", json={"token": _token_from(outbox[-1]["body"])})
    old_refresh = _login(client, email, "OriginalPass1!").json()["refresh_token"]

    assert (
        client.post(f"{API}/auth/password-reset/request", json={"email": email}).status_code == 202
    )
    # Unknown email gets the same 202 — no account enumeration
    assert (
        client.post(
            f"{API}/auth/password-reset/request", json={"email": _unique_email()}
        ).status_code
        == 202
    )
    reset_token = _token_from(outbox[-1]["body"])
    response = client.post(
        f"{API}/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 200
    assert _login(client, email, "OriginalPass1!").status_code == 401
    assert _login(client, email, "BrandNewPass1!").status_code == 200
    # Reset revoked every outstanding refresh token (TRD §9)
    assert (
        client.post(f"{API}/auth/refresh", json={"refresh_token": old_refresh}).status_code == 401
    )
    # Reset tokens are single-use
    assert (
        client.post(
            f"{API}/auth/password-reset/confirm",
            json={"token": reset_token, "new_password": "AnotherPass1!"},
        ).status_code
        == 400
    )


# --- Checkpoint: invite-based provisioning for staff roles ---


def test_invite_flow_creates_agent(client, outbox):
    admin = _login(client, SEED_USERS["admin"]).json()["access_token"]
    email = _unique_email()
    response = client.post(
        f"{API}/users",
        json={"email": email, "full_name": "Invited Agent", "role": "agent"},
        headers=_auth(admin),
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "agent"
    invite_token = _token_from(outbox[-1]["body"])
    confirm = client.post(
        f"{API}/auth/password-reset/confirm",
        json={"token": invite_token, "new_password": "InvitedPass1!"},
    )
    assert confirm.status_code == 200
    login = _login(client, email, "InvitedPass1!")
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "agent"


# --- Checkpoint + AC3: lower roles rejected by every admin-only endpoint ---


def test_admin_only_endpoints_reject_requester_and_agent(client):
    admin = _login(client, SEED_USERS["admin"]).json()
    some_user_id = admin["user"]["id"]
    for role in ("requester", "agent"):
        token = _login(client, SEED_USERS[role]).json()["access_token"]
        attempts = [
            client.post(
                f"{API}/users",
                json={"email": _unique_email(), "full_name": "X", "role": "admin"},
                headers=_auth(token),
            ),
            client.patch(
                f"{API}/users/{some_user_id}", json={"role": "requester"}, headers=_auth(token)
            ),
            client.delete(f"{API}/users/{some_user_id}", headers=_auth(token)),
        ]
        for response in attempts:
            assert response.status_code == 403, (role, response.request.url, response.text)
    # GET /users is Admin/Team Lead only
    requester = _login(client, SEED_USERS["requester"]).json()["access_token"]
    agent = _login(client, SEED_USERS["agent"]).json()["access_token"]
    assert client.get(f"{API}/users", headers=_auth(requester)).status_code == 403
    assert client.get(f"{API}/users", headers=_auth(agent)).status_code == 403
    lead = _login(client, SEED_USERS["team_lead"]).json()["access_token"]
    assert client.get(f"{API}/users", headers=_auth(lead)).status_code == 200


def test_requester_profile_scope(client):
    requester = _login(client, SEED_USERS["requester"]).json()
    admin_id = _login(client, SEED_USERS["admin"]).json()["user"]["id"]
    token = requester["access_token"]
    own_id = requester["user"]["id"]
    assert client.get(f"{API}/users/{own_id}", headers=_auth(token)).status_code == 200
    assert client.get(f"{API}/users/{admin_id}", headers=_auth(token)).status_code == 403
    # Self-service profile fields are editable; role escalation is not
    assert (
        client.patch(
            f"{API}/users/{own_id}", json={"theme_preference": "dark"}, headers=_auth(token)
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{API}/users/{own_id}", json={"role": "admin"}, headers=_auth(token)
        ).status_code
        == 403
    )


def test_deactivated_user_loses_access_immediately(client, outbox):
    email = _unique_email()
    client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "DoomedPass1!", "full_name": "Doomed"},
    )
    client.post(f"{API}/auth/verify-email", json={"token": _token_from(outbox[-1]["body"])})
    tokens = _login(client, email, "DoomedPass1!").json()
    admin = _login(client, SEED_USERS["admin"]).json()["access_token"]
    assert (
        client.delete(f"{API}/users/{tokens['user']['id']}", headers=_auth(admin)).status_code
        == 204
    )
    assert _login(client, email, "DoomedPass1!").status_code == 403
    # Even an unexpired access token dies with the account (fresh DB check per request)
    own = client.get(f"{API}/users/{tokens['user']['id']}", headers=_auth(tokens["access_token"]))
    assert own.status_code == 401
    refreshed = client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 401


# --- scope_tickets_to_caller primitive (full HTTP test lands with Phase 4 tickets) ---


def test_scope_tickets_to_caller_criteria():
    user = SimpleNamespace(id=uuid.uuid4(), team_id=uuid.uuid4())
    tickets = SimpleNamespace(
        requester_id=sa.column("requester_id"),
        assignee_id=sa.column("assignee_id"),
        queue_id=sa.column("queue_id"),
    )
    queues = SimpleNamespace(id=sa.column("id"), team_id=sa.column("team_id"))
    users = SimpleNamespace(id=sa.column("id"), team_id=sa.column("team_id"))

    def compiled(role):
        return str(scope_tickets_to_caller(user, role, tickets, queues, users))

    assert compiled("admin") == "true"
    assert compiled("requester") == "requester_id = :requester_id_1"
    agent_sql = compiled("agent")
    assert "assignee_id" in agent_sql and "queue_id IN" in agent_sql
    lead_sql = compiled("team_lead")
    assert "queue_id IN" in lead_sql and "assignee_id IN" in lead_sql
    assert compiled("unknown") == "false"
