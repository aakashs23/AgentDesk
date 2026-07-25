"""Phase 6 checkpoint: SLA warning → escalation on a short threshold, rules
firing on creation, an execution-log row for every evaluation (including
non-matching), and priority-ordered conflict resolution, visibly logged.

Runs against the migrated + seeded database. The SLA scan is driven directly
(scan_once) instead of waiting for the background interval.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.sla import monitor

SEED_PASSWORD = "Password123!"
API = "/api/v1"


@pytest.fixture(scope="module")
def db():
    engine = sa.create_engine(get_settings().database_url.replace("+asyncpg", "+psycopg2"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def tokens(client) -> dict[str, str]:
    out = {}
    for role, email in [
        ("requester", "requester@agentdesk.dev"),
        ("agent", "agent@agentdesk.dev"),
        ("team_lead", "lead@agentdesk.dev"),
        ("admin", "admin@agentdesk.dev"),
    ]:
        response = client.post(
            f"{API}/auth/login", json={"email": email, "password": SEED_PASSWORD}
        )
        out[role] = response.json()["access_token"]
    return out


@pytest.fixture(scope="module")
def ids(db) -> dict[str, str]:
    with db.connect() as conn:
        return {
            "billing": str(
                conn.execute(sa.text("SELECT id FROM categories WHERE name='Billing'")).scalar()
            ),
            "tech": str(
                conn.execute(
                    sa.text("SELECT id FROM categories WHERE name='Technical Support'")
                ).scalar()
            ),
            "queue": str(conn.execute(sa.text("SELECT id FROM queues LIMIT 1")).scalar()),
            "critical": str(
                conn.execute(sa.text("SELECT id FROM priorities WHERE name='Critical'")).scalar()
            ),
            "lead": str(
                conn.execute(
                    sa.text("SELECT id FROM users WHERE email='lead@agentdesk.dev'")
                ).scalar()
            ),
            "agent": str(
                conn.execute(
                    sa.text("SELECT id FROM users WHERE email='agent@agentdesk.dev'")
                ).scalar()
            ),
        }


@pytest.fixture(autouse=True)
def no_pipeline(monkeypatch):
    # Phase 6 tests exercise automation, not the AI pipeline
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")


@pytest.fixture
def cleanup_rules(client, tokens, db):
    yield
    # deactivate every rule so suites/tests stay independent
    with db.begin() as conn:
        conn.execute(sa.text("UPDATE automation_rules SET is_active = false"))


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _mkrule(client, tokens, **overrides) -> dict:
    body = {
        "name": "test rule",
        "trigger_type": "ticket_created",
        "conditions": [],
        "actions": [],
        "priority": 100,
        **overrides,
    }
    response = client.post(
        f"{API}/admin/automation-rules", json=body, headers=_auth(tokens["admin"])
    )
    assert response.status_code == 201, response.text
    return response.json()


def _mkticket(client, tokens, category_id=None, subject="automation test") -> dict:
    body = {"subject": subject, "description": "body", "channel": "portal"}
    if category_id:
        body["category_id"] = category_id
    response = client.post(f"{API}/tickets", json=body, headers=_auth(tokens["requester"]))
    assert response.status_code == 201, response.text
    return response.json()


def _logs(client, tokens, **params) -> list[dict]:
    response = client.get(
        f"{API}/admin/automation-logs", params=params, headers=_auth(tokens["admin"])
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_rule_crud_is_admin_only(client, tokens):
    response = client.post(
        f"{API}/admin/automation-rules",
        json={"name": "x", "trigger_type": "ticket_created"},
        headers=_auth(tokens["agent"]),
    )
    assert response.status_code == 403
    response = client.post(
        f"{API}/admin/automation-rules",
        json={"name": "x", "trigger_type": "bogus_trigger"},
        headers=_auth(tokens["admin"]),
    )
    assert response.status_code == 422


def test_matching_rule_fires_on_creation(client, tokens, ids, cleanup_rules):
    rule = _mkrule(
        client,
        tokens,
        name="billing to queue",
        conditions=[{"field": "category_id", "op": "eq", "value": ids["billing"]}],
        actions=[{"type": "assign", "queue_id": ids["queue"]}],
    )
    ticket = _mkticket(client, tokens, category_id=ids["billing"])
    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["admin"])).json()
    assert got["queue_id"] == ids["queue"]
    assert got["status"] == "open"  # rule-driven assignment moves New → Open

    logs = _logs(client, tokens, ticket_id=ticket["id"])
    assert [(row["automation_rule_id"], row["execution_status"]) for row in logs] == [
        (rule["id"], "success")
    ]


def test_non_matching_rule_is_logged_skipped(client, tokens, ids, cleanup_rules):
    rule = _mkrule(
        client,
        tokens,
        name="tech only",
        conditions=[{"field": "category_id", "op": "eq", "value": ids["tech"]}],
        actions=[{"type": "assign", "queue_id": ids["queue"]}],
    )
    ticket = _mkticket(client, tokens, category_id=ids["billing"])
    logs = _logs(client, tokens, ticket_id=ticket["id"])
    assert [(row["automation_rule_id"], row["execution_status"]) for row in logs] == [
        (rule["id"], "skipped")
    ]
    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["admin"])).json()
    assert got["queue_id"] is None


def test_conflicting_rules_resolve_by_priority(client, tokens, ids, db, cleanup_rules):
    winner = _mkrule(
        client,
        tokens,
        name="assign to agent (wins)",
        priority=1,
        actions=[{"type": "assign", "assignee_id": ids["agent"]}],
    )
    loser = _mkrule(
        client,
        tokens,
        name="assign to lead (suppressed)",
        priority=2,
        actions=[{"type": "assign", "assignee_id": ids["lead"]}],
    )
    ticket = _mkticket(client, tokens)
    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["admin"])).json()
    assert got["assignee_id"] == ids["agent"]  # lower priority number won

    # both rules matched → both logged success; the conflict is in the audit log
    rows = _logs(client, tokens, ticket_id=ticket["id"])
    statuses = {row["automation_rule_id"]: row["execution_status"] for row in rows}
    assert statuses == {winner["id"]: "success", loser["id"]: "success"}
    with db.connect() as conn:
        conflict = conn.execute(
            sa.text(
                "SELECT after_state FROM audit_logs WHERE entity_id = :tid "
                "AND action = 'automation_conflict'"
            ),
            {"tid": ticket["id"]},
        ).scalar()
    assert conflict["suppressed_rule_id"] == loser["id"]


def test_failed_rule_logs_error_and_never_breaks_request(client, tokens, ids, cleanup_rules):
    rule = _mkrule(
        client,
        tokens,
        name="broken action",
        actions=[{"type": "assign", "queue_id": str(uuid.uuid4())}],  # unknown queue
    )
    ticket = _mkticket(client, tokens)  # still 201
    logs = _logs(client, tokens, ticket_id=ticket["id"])
    assert logs[0]["automation_rule_id"] == rule["id"]
    assert logs[0]["execution_status"] == "failed"
    assert "unknown queue" in logs[0]["error_message"]


def test_preview_returns_matching_sample(client, tokens, ids, cleanup_rules):
    _mkticket(client, tokens, category_id=ids["billing"], subject="preview me")
    response = client.post(
        f"{API}/admin/automation-rules/preview",
        json={"conditions": [{"field": "category_id", "op": "eq", "value": ids["billing"]}]},
        headers=_auth(tokens["admin"]),
    )
    assert response.status_code == 200, response.text
    sample = response.json()
    assert sample and all(t["category_id"] == ids["billing"] for t in sample)


def _run_scan() -> int:
    async def go() -> int:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with async_sessionmaker(engine)() as session:
                fired = await monitor.scan_once(session)
                await session.commit()
                return fired
        finally:
            await engine.dispose()

    return asyncio.run(go())


def test_sla_warning_then_escalation(client, tokens, ids, db, cleanup_rules):
    tag_rule = _mkrule(
        client,
        tokens,
        name="tag on breach",
        trigger_type="sla_breached",
        actions=[],  # matched with no actions — proves the trigger fires
    )
    ticket = _mkticket(client, tokens, category_id=ids["billing"])
    # classify Critical via admin so SLA timers start, and self-assign the agent
    client.patch(
        f"{API}/tickets/{ticket['id']}",
        json={"priority_id": ids["critical"]},
        headers=_auth(tokens["admin"]),
    )
    client.post(
        f"{API}/tickets/{ticket['id']}/assign",
        json={"assignee_id": ids["agent"], "queue_id": ids["queue"]},
        headers=_auth(tokens["admin"]),
    )

    # 1) inside the warning window → warning notification to the assignee
    warn_at = datetime.now(UTC) + timedelta(minutes=get_settings().sla_warning_minutes - 5)
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE tickets SET resolution_due_at = :due WHERE id = :tid"),
            {"due": warn_at, "tid": ticket["id"]},
        )
    assert _run_scan() >= 1
    with db.connect() as conn:
        warned = conn.execute(
            sa.text(
                "SELECT user_id FROM notifications WHERE ticket_id = :tid "
                "AND trigger_type = 'sla_warning'"
            ),
            {"tid": ticket["id"]},
        ).scalar()
    assert str(warned) == ids["agent"]

    # scanning again does not duplicate the warning
    _run_scan()
    with db.connect() as conn:
        count = conn.execute(
            sa.text(
                "SELECT count(*) FROM notifications WHERE ticket_id = :tid "
                "AND trigger_type = 'sla_warning'"
            ),
            {"tid": ticket["id"]},
        ).scalar()
    assert count == 1

    # 2) past the deadline → escalation to the team lead + sla_breached trigger
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE tickets SET resolution_due_at = now() - interval '1 minute' WHERE id = :tid"
            ),
            {"tid": ticket["id"]},
        )
    assert _run_scan() >= 1
    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["admin"])).json()
    assert got["assignee_id"] == ids["lead"]
    with db.connect() as conn:
        breach = conn.execute(
            sa.text(
                "SELECT user_id FROM notifications WHERE ticket_id = :tid "
                "AND trigger_type = 'sla_breached'"
            ),
            {"tid": ticket["id"]},
        ).scalar()
        escalated = conn.execute(
            sa.text(
                "SELECT count(*) FROM audit_logs WHERE entity_id = :tid "
                "AND action = 'sla_escalated'"
            ),
            {"tid": ticket["id"]},
        ).scalar()
    assert str(breach) == ids["lead"]
    assert escalated == 1

    # the sla_breached automation trigger evaluated the rule (visible in logs)
    logs = _logs(client, tokens, ticket_id=ticket["id"], rule_id=tag_rule["id"])
    assert logs and logs[0]["execution_status"] == "success"


def test_delete_with_history_deactivates_instead(client, tokens, ids, cleanup_rules):
    rule = _mkrule(client, tokens, name="short lived")
    _mkticket(client, tokens)  # generates an execution log for the rule
    response = client.delete(
        f"{API}/admin/automation-rules/{rule['id']}", headers=_auth(tokens["admin"])
    )
    assert response.status_code == 409
    response = client.patch(
        f"{API}/admin/automation-rules/{rule['id']}",
        json={"is_active": False},
        headers=_auth(tokens["admin"]),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False
