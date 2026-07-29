"""Phase 4 checkpoint: full ticket lifecycle through the API, complete dual audit
trail, fresh SLA segment on reopen, clean attachment rejection, RBAC scoping.

Runs against the migrated + seeded database.
"""

import re
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.notifications import mailer

SEED_PASSWORD = "Password123!"
SEED_USERS = {
    "requester": "requester@agentdesk.dev",
    "agent": "agent@agentdesk.dev",
    "team_lead": "lead@agentdesk.dev",
    "admin": "admin@agentdesk.dev",
}
API = "/api/v1"


@pytest.fixture(scope="module")
def db():
    engine = sa.create_engine(get_settings().database_url.replace("+asyncpg", "+psycopg2"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def tokens(client) -> dict[str, str]:
    out = {}
    for role, email in SEED_USERS.items():
        response = client.post(
            f"{API}/auth/login", json={"email": email, "password": SEED_PASSWORD}
        )
        out[role] = response.json()["access_token"]
    return out


@pytest.fixture(scope="module")
def user_ids(client, tokens) -> dict[str, str]:
    ids = {}
    for role, email in SEED_USERS.items():
        response = client.post(
            f"{API}/auth/login", json={"email": email, "password": SEED_PASSWORD}
        )
        ids[role] = response.json()["user"]["id"]
    return ids


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _create(client, tokens, role="requester", **overrides) -> dict:
    body = {"subject": "Printer on fire", "description": "It is very much on fire."}
    body.update(overrides)
    response = client.post(f"{API}/tickets", json=body, headers=_auth(tokens[role]))
    assert response.status_code == 201, response.text
    return response.json()


def _set_status(client, token, ticket_id, status):
    return client.patch(
        f"{API}/tickets/{ticket_id}/status", json={"status": status}, headers=_auth(token)
    )


def _assign_to_agent(client, tokens, user_ids, ticket_id) -> dict:
    """Unrouted tickets are only visible org-wide (admin) until Phase 5 routing —
    admin assigns, which also performs the manual New → Open pickup."""
    response = client.post(
        f"{API}/tickets/{ticket_id}/assign",
        json={"assignee_id": user_ids["agent"]},
        headers=_auth(tokens["admin"]),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _priority_id(db) -> str:
    with db.connect() as conn:
        return str(conn.execute(sa.text("SELECT id FROM priorities LIMIT 1")).scalar_one())


# --- Checkpoint: full lifecycle through the API with a complete dual trail ---


def test_full_lifecycle_and_dual_audit_trail(client, db, tokens, user_ids):
    ticket = _create(client, tokens)
    assert ticket["status"] == "new"
    assert ticket["ref"] == f"AGT-{ticket['display_id']}"
    tid = ticket["id"]

    assert _assign_to_agent(client, tokens, user_ids, tid)["status"] == "open"

    agent = tokens["agent"]
    # First public agent reply: Open → In Progress (§10)
    reply = client.post(
        f"{API}/tickets/{tid}/comments", json={"body": "On it."}, headers=_auth(agent)
    )
    assert reply.status_code == 201
    assert (
        client.get(f"{API}/tickets/{tid}", headers=_auth(agent)).json()["status"] == "in_progress"
    )

    assert _set_status(client, agent, tid, "on_hold").json()["status"] == "on_hold"
    # Requester reply auto-resumes: On Hold → In Progress, system-attributed
    client.post(
        f"{API}/tickets/{tid}/comments",
        json={"body": "Here is the info you asked for"},
        headers=_auth(tokens["requester"]),
    )
    assert (
        client.get(f"{API}/tickets/{tid}", headers=_auth(agent)).json()["status"] == "in_progress"
    )

    resolved = _set_status(client, agent, tid, "resolved").json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    closed = _set_status(client, agent, tid, "closed").json()
    assert closed["status"] == "closed" and closed["closed_at"]

    reopened = client.post(f"{API}/tickets/{tid}/reopen", headers=_auth(tokens["requester"]))
    body = reopened.json()
    assert reopened.status_code == 200
    # §10: Reopened → In Progress is automatic re-entry
    assert body["status"] == "in_progress"
    assert body["reopened_count"] == 1
    assert body["resolved_at"] is None and body["closed_at"] is None

    history = client.get(
        f"{API}/tickets/{tid}/status-history", headers=_auth(tokens["admin"])
    ).json()
    assert [(row["old_status"], row["new_status"]) for row in history] == [
        (None, "new"),
        ("new", "open"),
        ("open", "in_progress"),
        ("in_progress", "on_hold"),
        ("on_hold", "in_progress"),
        ("in_progress", "resolved"),
        ("resolved", "closed"),
        ("closed", "reopened"),
        ("reopened", "in_progress"),
    ]
    # The on_hold→in_progress resume was system-attributed (requester reply)
    assert history[4]["changed_by"] is None
    assert history[8]["changed_by"] is None

    # Both trail tables carry the same, complete transition record (the invariant)
    with db.connect() as conn:
        audit_actions = conn.execute(
            sa.text(
                "SELECT action, before_state->>'status', after_state->>'status' "
                "FROM audit_logs WHERE entity_type = 'ticket' AND entity_id = :tid "
                "AND action IN ('created', 'status_changed') ORDER BY created_at"
            ),
            {"tid": tid},
        ).all()
    assert len(audit_actions) == len(history)
    assert [(row[1], row[2]) for row in audit_actions] == [
        (row["old_status"], row["new_status"]) for row in history
    ]
    # Non-status actions were audited too
    with db.connect() as conn:
        actions = {
            row[0]
            for row in conn.execute(
                sa.text(
                    "SELECT DISTINCT action FROM audit_logs "
                    "WHERE entity_type = 'ticket' AND entity_id = :tid"
                ),
                {"tid": tid},
            )
        }
    assert "assigned" in actions


# --- Checkpoint: only §10 transitions are legal; roles enforced ---


def test_illegal_transitions_rejected(client, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    admin = tokens["admin"]
    for bad in ("resolved", "closed", "on_hold", "nonsense"):
        response = _set_status(client, admin, tid, bad)
        assert response.status_code == 409, (bad, response.text)
    # Requester may not perform staff transitions, even on their own ticket
    assert _set_status(client, tokens["requester"], tid, "open").status_code == 403
    # reopened→* is system-only; a closed ticket can't jump straight to in_progress
    _assign_to_agent(client, tokens, user_ids, tid)
    assert _set_status(client, admin, tid, "reopened").status_code == 409  # open, not closed
    assert _set_status(client, admin, tid, "new").status_code == 409


# --- Checkpoint: SLA timers — set on classification, fresh segment on reopen ---


def test_sla_set_on_classification_and_fresh_segment_on_reopen(client, db, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    assert ticket["response_due_at"] is None  # unclassified: no priority, no policy yet
    _assign_to_agent(client, tokens, user_ids, tid)

    agent = tokens["agent"]
    classified = client.patch(
        f"{API}/tickets/{tid}",
        json={"priority_id": _priority_id(db)},
        headers=_auth(agent),
    ).json()
    assert classified["response_due_at"] and classified["resolution_due_at"]
    original_due = _iso(classified["resolution_due_at"])

    client.post(f"{API}/tickets/{tid}/comments", json={"body": "ack"}, headers=_auth(agent))
    _set_status(client, agent, tid, "resolved")
    _set_status(client, agent, tid, "closed")
    reopened = client.post(f"{API}/tickets/{tid}/reopen", headers=_auth(tokens["requester"])).json()
    fresh_due = _iso(reopened["resolution_due_at"])
    # Fresh segment anchored at reopen time — never the original creation-anchored clock
    assert fresh_due > original_due


def test_on_hold_pauses_resolution_timer(client, db, tokens, user_ids):
    import time

    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    agent = tokens["agent"]
    before = client.patch(
        f"{API}/tickets/{tid}", json={"priority_id": _priority_id(db)}, headers=_auth(agent)
    ).json()["resolution_due_at"]
    client.post(f"{API}/tickets/{tid}/comments", json={"body": "ack"}, headers=_auth(agent))
    _set_status(client, agent, tid, "on_hold")
    time.sleep(0.2)
    resumed = _set_status(client, agent, tid, "in_progress").json()
    # Deadline pushed out by the hold duration
    assert _iso(resumed["resolution_due_at"]) > _iso(before)


# --- Checkpoint: reopen window ---


def test_reopen_window_elapsed(client, db, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    agent = tokens["agent"]
    client.post(f"{API}/tickets/{tid}/comments", json={"body": "ack"}, headers=_auth(agent))
    _set_status(client, agent, tid, "resolved")
    _set_status(client, agent, tid, "closed")
    with db.begin() as conn:  # age the closure past the window
        conn.execute(
            sa.text(
                "UPDATE tickets SET closed_at = closed_at - interval '30 days' WHERE id = :tid"
            ),
            {"tid": tid},
        )
    response = client.post(f"{API}/tickets/{tid}/reopen", headers=_auth(tokens["requester"]))
    assert response.status_code == 409


# --- Checkpoint: RBAC — a requester sees only their own tickets ---


def test_requester_cannot_reach_another_requesters_ticket(client, tokens, monkeypatch):
    outbox: list[dict] = []
    monkeypatch.setattr(
        mailer, "send_email", lambda to, subject, body: outbox.append({"body": body})
    )
    email = f"other-{uuid.uuid4().hex[:8]}@agentdesk.dev"
    client.post(
        f"{API}/auth/register",
        json={"email": email, "password": "OtherPass1!", "full_name": "Other Requester"},
    )
    token = re.search(r"token=([A-Za-z0-9_\-]+)", outbox[-1]["body"]).group(1)
    client.post(f"{API}/auth/verify-email", json={"token": token})
    other = client.post(
        f"{API}/auth/login", json={"email": email, "password": "OtherPass1!"}
    ).json()["access_token"]

    ticket = _create(client, tokens)  # belongs to the seeded requester
    tid = ticket["id"]
    assert client.get(f"{API}/tickets/{tid}", headers=_auth(other)).status_code == 404
    listed = client.get(f"{API}/tickets", headers=_auth(other)).json()
    assert tid not in [t["id"] for t in listed]
    assert (
        client.post(
            f"{API}/tickets/{tid}/comments", json={"body": "sneaky"}, headers=_auth(other)
        ).status_code
        == 404
    )


def test_status_history_is_lead_and_admin_only(client, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    for role in ("requester", "agent"):
        response = client.get(f"{API}/tickets/{tid}/status-history", headers=_auth(tokens[role]))
        assert response.status_code == 403, role
    # Assignee is on the lead's team, so the ticket is in the lead's scope
    assert (
        client.get(
            f"{API}/tickets/{tid}/status-history", headers=_auth(tokens["team_lead"])
        ).status_code
        == 200
    )


# --- Checkpoint: comments — internal notes, mentions, edit/delete rights ---


def test_internal_notes_hidden_from_requester(client, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    requester = tokens["requester"]
    assert (
        client.post(
            f"{API}/tickets/{tid}/comments",
            json={"body": "note to self", "is_internal": True},
            headers=_auth(requester),
        ).status_code
        == 403
    )
    client.post(
        f"{API}/tickets/{tid}/comments",
        json={"body": "internal: requester seems nice", "is_internal": True},
        headers=_auth(tokens["agent"]),
    )
    requester_view = client.get(f"{API}/tickets/{tid}/comments", headers=_auth(requester)).json()
    assert all(not c["is_internal"] for c in requester_view)
    agent_view = client.get(f"{API}/tickets/{tid}/comments", headers=_auth(tokens["agent"])).json()
    assert any(c["is_internal"] for c in agent_view)


def test_mention_parsing_writes_comment_mentions(client, db, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    comment = client.post(
        f"{API}/tickets/{tid}/comments",
        json={"body": "@lead@agentdesk.dev can you take a look?", "is_internal": True},
        headers=_auth(tokens["agent"]),
    ).json()
    with db.connect() as conn:
        mentioned = (
            conn.execute(
                sa.text("SELECT mentioned_user_id FROM comment_mentions WHERE comment_id = :cid"),
                {"cid": comment["id"]},
            )
            .scalars()
            .all()
        )
    assert [str(m) for m in mentioned] == [user_ids["team_lead"]]


def test_comment_edit_delete_author_or_admin(client, tokens):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    comment = client.post(
        f"{API}/tickets/{tid}/comments", json={"body": "v1"}, headers=_auth(tokens["requester"])
    ).json()
    cid = comment["id"]
    assert comment["updated_at"] is None
    # Author edits
    edited = client.patch(
        f"{API}/comments/{cid}", json={"body": "v2"}, headers=_auth(tokens["requester"])
    )
    assert edited.status_code == 200 and edited.json()["updated_at"] is not None
    # Non-author, non-admin cannot
    assert (
        client.patch(
            f"{API}/comments/{cid}", json={"body": "hax"}, headers=_auth(tokens["agent"])
        ).status_code
        == 403
    )
    # Admin can delete
    assert client.delete(f"{API}/comments/{cid}", headers=_auth(tokens["admin"])).status_code == 204


# --- Checkpoint: attachments — clean rejection, versioning, soft delete ---


def test_attachment_upload_download_reject_replace(client, tokens, monkeypatch):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    requester = tokens["requester"]

    up = client.post(
        f"{API}/tickets/{tid}/attachments",
        files={"file": ("screenshot.png", b"\x89PNG fake image bytes", "image/png")},
        headers=_auth(requester),
    )
    assert up.status_code == 201, up.text
    first = up.json()
    assert first["version"] == 1

    down = client.get(f"{API}/attachments/{first['id']}", headers=_auth(requester))
    assert down.status_code == 200
    assert down.content == b"\x89PNG fake image bytes"

    # Disallowed MIME → clean 415, not a 500
    bad = client.post(
        f"{API}/tickets/{tid}/attachments",
        files={"file": ("virus.exe", b"MZ...", "application/x-msdownload")},
        headers=_auth(requester),
    )
    assert bad.status_code == 415

    # Oversized → clean 413
    monkeypatch.setattr(get_settings(), "attachment_max_bytes", 8)
    big = client.post(
        f"{API}/tickets/{tid}/attachments",
        files={"file": ("big.png", b"123456789", "image/png")},
        headers=_auth(requester),
    )
    assert big.status_code == 413
    monkeypatch.undo()

    # Replace: version chain (Doc 05 §9 / App Flow §22)
    v2 = client.post(
        f"{API}/tickets/{tid}/attachments?replaces_attachment_id={first['id']}",
        files={"file": ("screenshot.png", b"better bytes", "image/png")},
        headers=_auth(requester),
    ).json()
    assert v2["version"] == 2
    refetched = client.get(f"{API}/attachments/{first['id']}", headers=_auth(requester))
    assert refetched.status_code == 200  # prior version never overwritten

    # Delete is staff-only, soft
    assert (
        client.delete(f"{API}/attachments/{v2['id']}", headers=_auth(requester)).status_code == 403
    )
    assert (
        client.delete(f"{API}/attachments/{v2['id']}", headers=_auth(tokens["admin"])).status_code
        == 204
    )
    assert client.get(f"{API}/attachments/{v2['id']}", headers=_auth(requester)).status_code == 404


# --- Checkpoint: tags ---


def test_tags_create_attach_requester_readonly(client, tokens, user_ids):
    tag_name = f"vip-{uuid.uuid4().hex[:6]}"
    assert (
        client.post(
            f"{API}/tags", json={"name": tag_name}, headers=_auth(tokens["requester"])
        ).status_code
        == 403
    )
    created = client.post(f"{API}/tags", json={"name": tag_name}, headers=_auth(tokens["agent"]))
    assert created.status_code == 201
    tag_id = created.json()["id"]
    assert (
        client.post(
            f"{API}/tags", json={"name": tag_name}, headers=_auth(tokens["agent"])
        ).status_code
        == 409
    )
    assert tag_name in [
        t["name"] for t in client.get(f"{API}/tags", headers=_auth(tokens["requester"])).json()
    ]

    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    attach = client.post(
        f"{API}/tickets/{tid}/tags", json={"tag_id": tag_id}, headers=_auth(tokens["agent"])
    )
    assert attach.status_code == 200
    again = client.post(
        f"{API}/tickets/{tid}/tags", json={"tag_id": tag_id}, headers=_auth(tokens["agent"])
    )
    assert again.status_code == 409


# --- Checkpoint: escalate, merge, split ---


def test_escalate_assigns_team_lead(client, tokens, user_ids):
    ticket = _create(client, tokens)
    tid = ticket["id"]
    _assign_to_agent(client, tokens, user_ids, tid)
    escalated = client.post(f"{API}/tickets/{tid}/escalate", headers=_auth(tokens["agent"]))
    assert escalated.status_code == 200
    assert escalated.json()["assignee_id"] == user_ids["team_lead"]


def test_merge_closes_secondary_and_links(client, tokens, user_ids):
    primary = _create(client, tokens, subject="Original problem")
    secondary = _create(client, tokens, subject="Duplicate problem")
    admin = tokens["admin"]
    merged = client.post(
        f"{API}/tickets/{secondary['id']}/merge",
        json={"target_ticket_id": primary["id"]},
        headers=_auth(admin),
    )
    assert merged.status_code == 200
    sec = client.get(f"{API}/tickets/{secondary['id']}", headers=_auth(admin)).json()
    assert sec["status"] == "closed"
    assert sec["merged_into_ticket_id"] == primary["id"]
    # System comment lands on the primary's thread
    comments = client.get(f"{API}/tickets/{primary['id']}/comments", headers=_auth(admin)).json()
    assert any("merged into this ticket" in c["body"] and c["author_id"] is None for c in comments)
    # A merged ticket cannot be reopened
    assert (
        client.post(f"{API}/tickets/{secondary['id']}/reopen", headers=_auth(admin)).status_code
        == 409
    )
    # Cannot merge into itself
    assert (
        client.post(
            f"{API}/tickets/{primary['id']}/merge",
            json={"target_ticket_id": primary["id"]},
            headers=_auth(admin),
        ).status_code
        == 422
    )


def test_split_creates_subtickets(client, tokens):
    parent = _create(client, tokens, subject="Two problems in one")
    admin = tokens["admin"]
    response = client.post(
        f"{API}/tickets/{parent['id']}/split",
        json={
            "subtickets": [
                {"subject": "Problem A", "description": "First half"},
                {"subject": "Problem B", "description": "Second half"},
            ]
        },
        headers=_auth(admin),
    )
    assert response.status_code == 201, response.text
    children = response.json()
    assert len(children) == 2
    assert all(c["status"] == "new" for c in children)
    assert all(c["requester_id"] == parent["requester_id"] for c in children)
    comments = client.get(f"{API}/tickets/{parent['id']}/comments", headers=_auth(admin)).json()
    assert any(c["body"].startswith("Split into:") for c in comments)
