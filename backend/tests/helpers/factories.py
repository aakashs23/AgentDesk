"""Factories for the entities the API can create.

Every factory suffixes a random token onto names/emails/subjects. That is what
gives tests isolation: the suite runs against a live Postgres with no per-test
rollback (the app opens its own session per request), so two tests must never be
able to collide on a unique column or a search term.

Factories that need privileges take the token of a caller that has them; they
assert the expected status themselves so a test failure points at the assertion
under test, not at the setup.
"""

import uuid

from tests.helpers.auth import API, SEED_PASSWORD, auth


def rand(prefix: str = "") -> str:
    """Short unique token — the isolation primitive for the whole suite."""
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def unique_email(prefix: str = "user") -> str:
    # example.com, not .test — pydantic's EmailStr rejects special-use TLDs.
    return f"{prefix}-{rand()}@example.com"


# --- Users ---


def register_requester(client, password: str = "Password123!", **overrides) -> dict:
    """Self-service registration. Returns {user, email, password, token?}.

    The account still needs email verification before it can log in, so the
    returned dict has no token; use `verified_requester` for a usable login.
    """
    body = {
        "email": unique_email("requester"),
        "password": password,
        "full_name": f"Test Requester {rand()}",
        **overrides,
    }
    response = client.post(f"{API}/auth/register", json=body)
    assert response.status_code == 201, response.text
    return {"user": response.json(), **body}


def verified_requester(client, db, **overrides) -> dict:
    """A registered requester with email_verified_at forced on, plus a token."""
    import sqlalchemy as sa

    created = register_requester(client, **overrides)
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE users SET email_verified_at = now() WHERE email = :e"),
            {"e": created["email"]},
        )
    from tests.helpers.auth import token_for

    created["token"] = token_for(client, created["email"], created["password"])
    return created


def invite_user(client, admin_token: str, role: str, team_id: str | None = None, **overrides):
    """Admin-provisioned account (invite flow). Returns the API response."""
    body = {
        "email": unique_email(role),
        "full_name": f"Test {role} {rand()}",
        "role": role,
        **overrides,
    }
    if team_id is not None:
        body["team_id"] = team_id
    return client.post(f"{API}/users", json=body, headers=auth(admin_token))


def activated_user(client, db, admin_token: str, role: str, team_id: str | None = None) -> dict:
    """Invite a user, force-verify, set a known password, and log in.

    Bypasses the emailed invite token on purpose: the invite flow itself is
    covered by the auth integration tests, and every other test just needs an
    account of a given role that can authenticate.
    """
    import bcrypt
    import sqlalchemy as sa

    response = invite_user(client, admin_token, role, team_id)
    assert response.status_code == 201, response.text
    user = response.json()
    pw_hash = bcrypt.hashpw(SEED_PASSWORD.encode(), bcrypt.gensalt()).decode()
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE users SET email_verified_at = now(), password_hash = :h WHERE id = :i"),
            {"h": pw_hash, "i": user["id"]},
        )
    from tests.helpers.auth import token_for

    return {**user, "token": token_for(client, user["email"]), "password": SEED_PASSWORD}


# --- Tickets ---


def make_ticket(client, token: str, **overrides) -> dict:
    body = {
        "subject": f"Test ticket {rand()}",
        "description": f"Description {rand()}",
        "channel": "portal",
        **overrides,
    }
    response = client.post(f"{API}/tickets", json=body, headers=auth(token))
    assert response.status_code == 201, response.text
    return response.json()


def set_status(client, token: str, ticket_id: str, status: str):
    return client.patch(
        f"{API}/tickets/{ticket_id}/status", json={"status": status}, headers=auth(token)
    )


def drive_to(client, tokens, ticket_id: str, target: str, staff_role: str = "agent") -> None:
    """Walk a ticket through the legal §10 path to `target`, asserting each hop.

    Skips hops the ticket has already taken — assigning a queue moves New → Open
    on its own, so a caller that has assigned first must not re-request `open`
    (which is an illegal open → open transition).
    """
    path = ["open", "in_progress", "resolved", "closed"]
    assert target in path, target
    token = tokens[staff_role]

    current = client.get(f"{API}/tickets/{ticket_id}", headers=auth(token))
    assert current.status_code == 200, current.text
    status_now = current.json()["status"]
    start = path.index(status_now) + 1 if status_now in path else 0

    for status in path[start : path.index(target) + 1]:
        response = set_status(client, token, ticket_id, status)
        assert response.status_code == 200, f"{status}: {response.text}"


def run_on_app_loop(client, coro_fn):
    """Await `coro_fn()` on the TestClient's own portal loop.

    Not `asyncio.run`: asyncpg connections are bound to the loop that opened
    them, and the app's engine pool belongs to the portal loop. Driving app
    coroutines from a second loop hands out cross-loop connections and corrupts
    the pool for every later request — which surfaces as unrelated failures
    somewhere else entirely.
    """
    return client.portal.call(coro_fn)


def assign(client, token: str, ticket_id: str, assignee_id=None, queue_id=None):
    body = {}
    if assignee_id is not None:
        body["assignee_id"] = assignee_id
    if queue_id is not None:
        body["queue_id"] = queue_id
    return client.post(f"{API}/tickets/{ticket_id}/assign", json=body, headers=auth(token))


def comment(client, token: str, ticket_id: str, body: str | None = None, is_internal: bool = False):
    return client.post(
        f"{API}/tickets/{ticket_id}/comments",
        json={
            "body": body if body is not None else f"Comment {rand()}",
            "is_internal": is_internal,
        },
        headers=auth(token),
    )


# --- Tags ---


def make_tag(client, staff_token: str, name: str | None = None) -> dict:
    response = client.post(
        f"{API}/tags", json={"name": name or rand("tag-")}, headers=auth(staff_token)
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- Automation rules ---


def make_rule(client, admin_token: str, **overrides) -> dict:
    body = {
        "name": f"rule-{rand()}",
        "trigger_type": "ticket_created",
        "conditions": [],
        "actions": [],
        "priority": 100,
        "is_active": True,
        **overrides,
    }
    response = client.post(f"{API}/admin/automation-rules", json=body, headers=auth(admin_token))
    assert response.status_code == 201, response.text
    return response.json()


def delete_rule(client, admin_token: str, rule_id: str) -> None:
    """Best-effort teardown — a rule with execution history cannot be deleted."""
    response = client.delete(f"{API}/admin/automation-rules/{rule_id}", headers=auth(admin_token))
    if response.status_code == 409:
        client.patch(
            f"{API}/admin/automation-rules/{rule_id}",
            json={"is_active": False},
            headers=auth(admin_token),
        )


# --- Direct-to-DB reference data ---


def catalog(db) -> dict:
    """Ids of the seeded reference rows every test needs (priorities, queue, ...)."""
    import sqlalchemy as sa

    with db.connect() as conn:
        priorities = {
            name: str(pid)
            for name, pid in conn.execute(sa.text("SELECT name, id FROM priorities")).all()
        }
        categories = {
            name: str(cid)
            for name, cid in conn.execute(sa.text("SELECT name, id FROM categories")).all()
        }
        queue_id = conn.execute(sa.text("SELECT id FROM queues LIMIT 1")).scalar()
        team_id = conn.execute(sa.text("SELECT id FROM teams LIMIT 1")).scalar()
    return {
        "priorities": priorities,
        "categories": categories,
        "queue_id": str(queue_id),
        "team_id": str(team_id),
    }


def make_team(db, name: str | None = None) -> str:
    """A throwaway team. There is no team CRUD API, so this inserts directly.

    Use this instead of the seeded team whenever a test creates an agent or a
    team lead: `escalate_ticket` and `automation._find_team_lead` both pick a
    lead with `.limit(1)` and no ORDER BY, so a second lead on the seeded team
    makes every escalation test in the suite non-deterministic.
    """
    import sqlalchemy as sa

    team_id = uuid.uuid4()
    with db.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO teams (id, name) VALUES (:i, :n)"),
            {"i": team_id, "n": name or rand("team-")},
        )
    return str(team_id)


def make_kb_article(db, title: str, body: str, status: str = "published") -> str:
    """Knowledge base articles have no write API yet — insert directly."""
    import sqlalchemy as sa

    article_id = uuid.uuid4()
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_base_articles (id, title, body, status, published_at) "
                "VALUES (:id, :t, :b, :s, now())"
            ),
            {"id": article_id, "t": title, "b": body, "s": status},
        )
    return str(article_id)
