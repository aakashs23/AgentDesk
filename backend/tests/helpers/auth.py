"""Login helpers and token plumbing.

Everything the suite needs to talk to the API as a given role, in one place, so
no test hand-rolls a login POST or an Authorization header.
"""

API = "/api/v1"
SEED_PASSWORD = "Password123!"
SEED_USERS = {
    "requester": "requester@agentdesk.dev",
    "agent": "agent@agentdesk.dev",
    "team_lead": "lead@agentdesk.dev",
    "admin": "admin@agentdesk.dev",
}
ROLES = tuple(SEED_USERS)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client, email: str, password: str = SEED_PASSWORD):
    """Raw login response — callers assert on the status themselves."""
    return client.post(f"{API}/auth/login", json={"email": email, "password": password})


def token_for(client, email: str, password: str = SEED_PASSWORD) -> str:
    response = login(client, email, password)
    assert response.status_code == 200, f"login failed for {email}: {response.text}"
    return response.json()["access_token"]


def seed_tokens(client) -> dict[str, str]:
    """Access token for each seeded demo role, keyed by role name."""
    return {role: token_for(client, email) for role, email in SEED_USERS.items()}


def refresh_token_for(client, email: str, password: str = SEED_PASSWORD) -> str:
    response = login(client, email, password)
    assert response.status_code == 200, response.text
    return response.json()["refresh_token"]


def link_token_from_outbox(outbox, email: str, subject_contains: str) -> str:
    """Pull the one-time token out of an emailed link.

    One address can receive several link emails (verify, then reset, then a
    second reset), so match on the subject and take the most recent — matching
    on the address alone silently returns the wrong token.
    """
    import re

    matches = [
        body
        for to, subject, body in outbox
        if to == email and subject_contains.lower() in subject.lower()
    ]
    assert matches, (
        f"no email to {email} with {subject_contains!r} in the subject; "
        f"outbox held: {[(t, s) for t, s, _ in outbox]}"
    )
    found = re.search(r"token=([\w\-]+)", matches[-1])
    assert found, f"no token in link email body: {matches[-1]!r}"
    return found.group(1)
