"""Attacks against the authentication surface.

Covers the token lifecycle (forge / tamper / expire / replay), credential
handling, and the enumeration side-channels an attacker uses to map accounts.
"""

import base64
import json
import time
import uuid

import pytest
from jose import jwt as jose_jwt

from app.auth import security
from tests.helpers import factories as f
from tests.helpers.assertions import assert_never_leaks_secrets, assert_status
from tests.helpers.auth import (
    API,
    SEED_PASSWORD,
    auth,
    link_token_from_outbox,
    login,
    refresh_token_for,
)

PROTECTED = f"{API}/tickets"


# --- Missing / malformed credentials ---


@pytest.mark.parametrize(
    "header,label",
    [
        (None, "no Authorization header"),
        ({"Authorization": ""}, "empty header"),
        ({"Authorization": "Bearer"}, "scheme with no token"),
        ({"Authorization": "Bearer "}, "scheme with empty token"),
        ({"Authorization": "Bearer not.a.jwt"}, "non-JWT garbage"),
        ({"Authorization": "Basic YWRtaW46YWRtaW4="}, "wrong auth scheme"),
        ({"Authorization": "Bearer " + "A" * 5000}, "oversized token"),
        ({"Authorization": "Bearer \x00\x01\x02"}, "control bytes in token"),
    ],
)
def test_unusable_credentials_are_rejected(client, header, label):
    response = client.get(PROTECTED, headers=header)
    assert_status(response, 401, label)


def test_bearer_token_of_a_deleted_user_is_rejected(client, db, tokens):
    """A token stays cryptographically valid after the account is removed."""
    import sqlalchemy as sa

    user = f.verified_requester(client, db)
    token = user["token"]
    user_id = user["user"]["id"]
    assert client.get(PROTECTED, headers=auth(token)).status_code == 200
    with db.begin() as conn:
        for table in ("refresh_tokens", "password_reset_tokens", "email_verification_tokens"):
            conn.execute(sa.text(f"DELETE FROM {table} WHERE user_id = :i"), {"i": user_id})
        conn.execute(sa.text("DELETE FROM users WHERE id = :i"), {"i": user_id})
    assert_status(client.get(PROTECTED, headers=auth(token)), 401, "token for deleted user")


# --- JWT forgery ---


def _parts(token: str) -> tuple[str, str, str]:
    head, payload, signature = token.split(".")
    return head, payload, signature


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def test_signature_tampering_is_rejected(client, tokens):
    head, payload, signature = _parts(tokens["requester"])
    forged = f"{head}.{payload}.{signature[:-4]}AAAA"
    assert_status(client.get(PROTECTED, headers=auth(forged)), 401, "tampered signature")


def test_alg_none_token_is_rejected(client, user_ids):
    """The classic 'alg: none' downgrade must not authenticate anyone."""
    head = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64({"sub": user_ids["admin"], "role": "admin", "exp": int(time.time()) + 600})
    for token in (f"{head}.{payload}.", f"{head}.{payload}.x"):
        assert_status(client.get(f"{API}/users", headers=auth(token)), 401, "alg=none")


def test_missing_signature_segment_is_rejected(client, tokens):
    head, payload, _ = _parts(tokens["admin"])
    assert_status(client.get(f"{API}/users", headers=auth(f"{head}.{payload}")), 401, "2-segment")


def test_token_signed_with_the_wrong_secret_is_rejected(client, user_ids):
    for wrong_secret in ("", "secret", "changeme", "a" * 64):
        forged = jose_jwt.encode(
            {"sub": user_ids["admin"], "role": "admin", "exp": int(time.time()) + 600},
            wrong_secret,
            algorithm="HS256",
        )
        assert_status(
            client.get(f"{API}/users", headers=auth(forged)), 401, f"secret={wrong_secret!r}"
        )


def test_expired_token_is_rejected(client, user_ids):
    from app.config import get_settings

    expired = jose_jwt.encode(
        {"sub": user_ids["admin"], "role": "admin", "exp": int(time.time()) - 60},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert_status(client.get(f"{API}/users", headers=auth(expired)), 401, "expired exp")


def test_role_claim_in_the_token_does_not_grant_privileges(client, db, tokens, user_ids):
    """Authorization must come from the database row, never the JWT claim.

    A validly-signed token whose `role` claim says admin but whose subject is a
    requester must still be treated as a requester.
    """
    from app.config import get_settings

    token = jose_jwt.encode(
        {
            "sub": user_ids["requester"],
            "role": "admin",
            "team_id": None,
            "exp": int(time.time()) + 600,
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert_status(client.get(f"{API}/users", headers=auth(token)), 403, "forged role claim")


def test_access_token_carries_no_sensitive_claims(tokens):
    _, payload, _ = _parts(tokens["admin"])
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    assert set(claims) <= {"sub", "role", "team_id", "exp"}, claims
    assert_never_leaks_secrets(claims)


# --- Refresh token lifecycle ---


def test_refresh_token_is_single_use(client):
    token = refresh_token_for(client, "requester@agentdesk.dev")
    assert_status(client.post(f"{API}/auth/refresh", json={"refresh_token": token}), 200)
    assert_status(
        client.post(f"{API}/auth/refresh", json={"refresh_token": token}), 401, "replayed token"
    )


@pytest.mark.parametrize("token", ["", "not-a-token", "x" * 500, str(uuid.uuid4()), "' OR 1=1 --"])
def test_bogus_refresh_tokens_are_rejected(client, token):
    assert_status(
        client.post(f"{API}/auth/refresh", json={"refresh_token": token}), 401, token[:20]
    )


def test_password_reset_revokes_every_refresh_token(client, db, outbox):
    """TRD §9: a reset must invalidate sessions an attacker may already hold."""
    user = f.verified_requester(client, db)
    stolen = refresh_token_for(client, user["email"], user["password"])

    client.post(f"{API}/auth/password-reset/request", json={"email": user["email"]})
    raw = link_token_from_outbox(outbox, user["email"], "Reset")
    assert_status(
        client.post(
            f"{API}/auth/password-reset/confirm",
            json={"token": raw, "new_password": "BrandNewPassword1!"},
        ),
        200,
    )
    assert_status(
        client.post(f"{API}/auth/refresh", json={"refresh_token": stolen}),
        401,
        "refresh token survived a password reset",
    )


def test_deactivation_takes_effect_immediately(client, db, tokens):
    """The access token is still unexpired — the DB read must reject it anyway."""
    user = f.activated_user(client, db, tokens["admin"], "agent")
    assert client.get(PROTECTED, headers=auth(user["token"])).status_code == 200
    assert_status(client.delete(f"{API}/users/{user['id']}", headers=auth(tokens["admin"])), 204)
    assert_status(client.get(PROTECTED, headers=auth(user["token"])), 401, "deactivated user")


# --- Credential handling ---


def test_login_rejects_wrong_password(client):
    assert_status(login(client, "admin@agentdesk.dev", "wrong-password"), 401)


def test_unverified_account_cannot_log_in(client):
    created = f.register_requester(client)
    response = login(client, created["email"], created["password"])
    assert_status(response, 403, "unverified account logged in")


def test_login_response_never_contains_a_hash(client):
    response = login(client, "admin@agentdesk.dev")
    assert_status(response, 200)
    assert_never_leaks_secrets(response.json())


def test_password_reset_does_not_confirm_whether_an_account_exists(client):
    """Both branches must return the same status and body (no enumeration)."""
    known = client.post(f"{API}/auth/password-reset/request", json={"email": "admin@agentdesk.dev"})
    unknown = client.post(
        f"{API}/auth/password-reset/request", json={"email": f.unique_email("ghost")}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_failed_login_gives_the_same_answer_for_unknown_and_wrong_password(client):
    unknown = login(client, f.unique_email("ghost"), "whatever")
    wrong = login(client, "admin@agentdesk.dev", "whatever")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json(), "error body distinguishes unknown accounts"


def test_reset_token_is_single_use(client, db, outbox):
    user = f.verified_requester(client, db)
    client.post(f"{API}/auth/password-reset/request", json={"email": user["email"]})
    raw = link_token_from_outbox(outbox, user["email"], "Reset")
    payload = {"token": raw, "new_password": "AnotherPassword1!"}
    assert_status(client.post(f"{API}/auth/password-reset/confirm", json=payload), 200)
    assert_status(
        client.post(f"{API}/auth/password-reset/confirm", json=payload), 400, "reused reset token"
    )


def test_stored_password_is_bcrypt_and_never_the_plaintext(db):
    import sqlalchemy as sa

    with db.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT password_hash FROM users WHERE email = 'admin@agentdesk.dev'")
        ).scalar_one()
    assert stored.startswith("$2b$"), stored[:10]
    assert SEED_PASSWORD not in stored
    assert security.verify_password(SEED_PASSWORD, stored)


# --- Session teardown ---


def test_logout_revokes_the_presented_refresh_token(client):
    token = refresh_token_for(client, "requester@agentdesk.dev")
    access = login(client, "requester@agentdesk.dev").json()["access_token"]
    assert_status(
        client.post(f"{API}/auth/logout", json={"refresh_token": token}, headers=auth(access)), 204
    )
    assert_status(client.post(f"{API}/auth/refresh", json={"refresh_token": token}), 401)


def test_logout_requires_authentication(client):
    token = refresh_token_for(client, "requester@agentdesk.dev")
    assert_status(client.post(f"{API}/auth/logout", json={"refresh_token": token}), 401)
