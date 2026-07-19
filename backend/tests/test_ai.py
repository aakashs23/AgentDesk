"""Phase 5 checkpoint: pipeline confidence branches, mandatory human-in-the-loop
draft review, rejected drafts never become comments, correction feedback loop.

Gemini + DistilBERT are faked — deterministic, no network. Runs against the
migrated + seeded database (TestClient executes background tasks in-process,
so monkeypatching app.ai.gemini reaches the pipeline).
"""

import uuid

import pytest
import sqlalchemy as sa

from app.ai import classifier, gemini, pipeline
from app.config import get_settings
from app.models import EMBEDDING_DIM

SEED_PASSWORD = "Password123!"
API = "/api/v1"

FAKE_VECTOR = [1.0] + [0.0] * (EMBEDDING_DIM - 1)


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
        # unrouted tickets (low/medium tier) have no queue/assignee yet, so per
        # Doc 05 §6 scoping only admin can see them for manual classification
        ("admin", "admin@agentdesk.dev"),
    ]:
        response = client.post(
            f"{API}/auth/login", json={"email": email, "password": SEED_PASSWORD}
        )
        out[role] = response.json()["access_token"]
    return out


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    """Deterministic stand-ins: 'refund' tickets classify high, 'mystery' low."""
    get_settings().gemini_api_key = get_settings().gemini_api_key or "test-key"

    async def fake_embed(text: str) -> list[float]:
        return FAKE_VECTOR

    async def fake_generate_json(prompt: str, schema: dict) -> dict:
        # Key off the ticket text only — the prompt also carries similar-ticket
        # subjects from previous tests/runs, which must not flip the branch.
        ticket_text = prompt.rsplit("Ticket:", 1)[-1].lower()
        if "mystery" in ticket_text:
            return {"category": "Refunds", "priority": "Low", "confidence": 30}
        if "invoice" in ticket_text:
            return {"category": "Invoices", "priority": "Medium", "confidence": 70}
        return {"category": "Refunds", "priority": "High", "confidence": 95}

    async def fake_generate_text(prompt: str) -> str:
        return "Thanks for reaching out — here is what to do next."

    def fake_predict(text: str):
        return ("Refunds", 0.9) if "refund" in text.lower() else None

    monkeypatch.setattr(gemini, "embed", fake_embed)
    monkeypatch.setattr(gemini, "generate_json", fake_generate_json)
    monkeypatch.setattr(gemini, "generate_text", fake_generate_text)
    monkeypatch.setattr(classifier, "predict", fake_predict)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create(client, tokens, subject: str, description: str) -> dict:
    response = client.post(
        f"{API}/tickets",
        json={"subject": subject, "description": description, "channel": "portal"},
        headers=_auth(tokens["requester"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _insights(client, tokens, ticket_id: str) -> dict:
    response = client.get(f"{API}/tickets/{ticket_id}/ai", headers=_auth(tokens["admin"]))
    assert response.status_code == 200, response.text
    return response.json()


def test_high_confidence_auto_routes(client, tokens, db):
    ticket = _create(client, tokens, "Refund my order", "I want a refund for order 123")
    data = _insights(client, tokens, ticket["id"])
    assert data["classification"]["confidence_tier"] == "high"
    # 0.6*95 + 0.4*90 = 93 (LLM and DistilBERT agree on Refunds)
    assert data["classification"]["confidence"] == pytest.approx(93.0)

    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["agent"])).json()
    assert got["category_id"] is not None
    assert got["queue_id"] is not None
    assert got["assignee_id"] is not None
    assert got["status"] == "open"  # auto-route moved New → Open with no agent action

    # draft exists but is pending — never a comment yet
    assert data["drafts"][0]["review_status"] == "pending"
    comments = client.get(
        f"{API}/tickets/{ticket['id']}/comments", headers=_auth(tokens["agent"])
    ).json()
    assert comments == []

    with db.connect() as conn:
        row = conn.execute(
            sa.text("SELECT 1 FROM embeddings WHERE ticket_id = :tid"), {"tid": ticket["id"]}
        ).first()
        assert row is not None


def test_low_confidence_stays_unclassified(client, tokens):
    ticket = _create(client, tokens, "mystery", "mystery contents nobody understands")
    data = _insights(client, tokens, ticket["id"])
    assert data["classification"]["confidence_tier"] == "low"
    assert data["drafts"] == []  # no draft for low confidence

    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["admin"])).json()
    assert got["category_id"] is None
    assert got["assignee_id"] is None
    assert got["status"] == "new"


def test_medium_confidence_suggests_then_agent_confirms(client, tokens):
    ticket = _create(client, tokens, "invoice question", "invoice number is wrong")
    data = _insights(client, tokens, ticket["id"])
    assert data["classification"]["confidence_tier"] == "medium"

    # suggestion only: ticket untouched until an agent confirms (admin here —
    # the unrouted ticket is not yet visible to a plain agent, Doc 05 §6)
    got = client.get(f"{API}/tickets/{ticket['id']}", headers=_auth(tokens["admin"])).json()
    assert got["category_id"] is None

    response = client.post(
        f"{API}/tickets/{ticket['id']}/classification/confirm", headers=_auth(tokens["admin"])
    )
    assert response.status_code == 200, response.text
    confirmed = response.json()
    assert confirmed["category_id"] == data["classification"]["predicted_category_id"]
    assert confirmed["queue_id"] is not None
    assert confirmed["status"] == "open"


def test_approved_draft_becomes_ai_comment(client, tokens):
    ticket = _create(client, tokens, "Refund me", "refund please")
    draft = _insights(client, tokens, ticket["id"])["drafts"][0]

    response = client.post(
        f"{API}/ai/drafts/{draft['id']}/review",
        json={"action": "approved"},
        headers=_auth(tokens["agent"]),
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["review_status"] == "approved"
    assert reviewed["final_comment_id"] is not None

    comments = client.get(
        f"{API}/tickets/{ticket['id']}/comments", headers=_auth(tokens["agent"])
    ).json()
    assert len(comments) == 1
    assert comments[0]["is_ai_generated"] is True
    assert comments[0]["body"] == draft["draft_content"]

    # a reviewed draft cannot be re-reviewed
    again = client.post(
        f"{API}/ai/drafts/{draft['id']}/review",
        json={"action": "rejected"},
        headers=_auth(tokens["agent"]),
    )
    assert again.status_code == 409


def test_rejected_draft_never_becomes_comment(client, tokens):
    ticket = _create(client, tokens, "Refund now", "refund my charge")
    draft = _insights(client, tokens, ticket["id"])["drafts"][0]

    response = client.post(
        f"{API}/ai/drafts/{draft['id']}/review",
        json={"action": "rejected"},
        headers=_auth(tokens["agent"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["review_status"] == "rejected"
    assert response.json()["final_comment_id"] is None

    comments = client.get(
        f"{API}/tickets/{ticket['id']}/comments", headers=_auth(tokens["agent"])
    ).json()
    assert comments == []
    # retained in ai_draft_history as an analytics record
    assert _insights(client, tokens, ticket["id"])["drafts"][0]["review_status"] == "rejected"


def test_correction_feeds_training_loop(client, tokens, db):
    ticket = _create(client, tokens, "mystery", "mystery again")

    with db.connect() as conn:
        category_id = str(
            conn.execute(sa.text("SELECT id FROM categories WHERE name = 'Bug Report'")).scalar()
        )
        priority_id = str(
            conn.execute(sa.text("SELECT id FROM priorities WHERE name = 'High'")).scalar()
        )

    response = client.post(
        f"{API}/tickets/{ticket['id']}/classification/correct",
        json={"category_id": category_id, "priority_id": priority_id},
        headers=_auth(tokens["admin"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["category_id"] == category_id
    assert response.json()["status"] == "open"  # correction finalizes routing

    data = _insights(client, tokens, ticket["id"])
    assert data["classification"]["was_overridden"] is True
    assert data["classification"]["corrected_category_id"] == category_id
    assert data["classification"]["corrected_priority_id"] == priority_id


def test_requester_cannot_access_ai_endpoints(client, tokens):
    ticket = _create(client, tokens, "Refund", "refund it")
    response = client.get(f"{API}/tickets/{ticket['id']}/ai", headers=_auth(tokens["requester"]))
    assert response.status_code == 403


def test_edited_draft_uses_agent_content(client, tokens):
    ticket = _create(client, tokens, "Refund pls", "refund the payment")
    draft = _insights(client, tokens, ticket["id"])["drafts"][0]

    response = client.post(
        f"{API}/ai/drafts/{draft['id']}/review",
        json={"action": "edited", "content": "Here is the corrected reply."},
        headers=_auth(tokens["agent"]),
    )
    assert response.status_code == 200, response.text
    comments = client.get(
        f"{API}/tickets/{ticket['id']}/comments", headers=_auth(tokens["agent"])
    ).json()
    assert comments[0]["body"] == "Here is the corrected reply."
    assert comments[0]["is_ai_generated"] is True


def test_pii_is_redacted_before_llm(monkeypatch, client, tokens):
    seen: list[str] = []

    async def spy_embed(text: str) -> list[float]:
        seen.append(text)
        return FAKE_VECTOR

    monkeypatch.setattr(gemini, "embed", spy_embed)
    _create(
        client,
        tokens,
        "Refund",
        "My card 4111 1111 1111 1111 was charged, mail me at jane@example.com",
    )
    assert seen, "pipeline did not run"
    assert "4111" not in seen[0]
    assert "jane@example.com" not in seen[0]
    assert "[CARD]" in seen[0] and "[EMAIL]" in seen[0]


def test_pipeline_failure_never_breaks_creation(monkeypatch, client, tokens):
    async def boom(text: str) -> list[float]:
        raise RuntimeError("provider down")

    monkeypatch.setattr(gemini, "embed", boom)
    ticket = _create(client, tokens, "Refund", "refund me")  # still 201
    assert uuid.UUID(ticket["id"])
    assert _insights(client, tokens, ticket["id"])["classification"] is None


def test_pipeline_skipped_without_api_key(monkeypatch, client, tokens):
    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    ticket = _create(client, tokens, "Refund", "refund me now")
    assert _insights(client, tokens, ticket["id"])["classification"] is None


def test_langgraph_wiring():
    """The pipeline is a compiled LangGraph graph with the §14 branch."""
    graph = pipeline.build_graph()
    nodes = set(graph.get_graph().nodes)
    assert {"redact", "embed", "retrieve", "classify", "route", "draft"} <= nodes
