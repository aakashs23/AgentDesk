"""The API surface the Agent Console (Phase 11) needs on top of Phases 4–10:
queue filters on `GET /tickets`, an agent-visible staff directory, and the
knowledge-base creation loop from App Flow §19.

The KB write half was listed in `test_api_surface.MISSING_ENDPOINTS` until now;
this file is the "real tests" that file asks for when a gap gets filled.
"""

import pytest

from app.models import EMBEDDING_DIM
from tests.helpers.auth import API, auth
from tests.helpers.factories import make_ticket, rand

# --- Queue tabs: My Tickets / Team Queue / Unassigned ---


def _ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {t["id"] for t in response.json()}


def test_the_three_queue_tabs_partition_by_assignment(client, tokens, db):
    ticket = make_ticket(client, tokens["requester"])
    directory = client.get(f"{API}/users", headers=auth(tokens["agent"]))
    assert directory.status_code == 200, directory.text
    agent_id = next(u["id"] for u in directory.json() if u["email"] == "agent@agentdesk.dev")

    # Before assignment it is in the unassigned tab and not in My Tickets.
    unassigned = client.get(
        f"{API}/tickets?unassigned=true&limit=100", headers=auth(tokens["admin"])
    )
    assert ticket["id"] in _ids(unassigned)

    mine = client.get(
        f"{API}/tickets?assignee_id={agent_id}&limit=100", headers=auth(tokens["admin"])
    )
    assert ticket["id"] not in _ids(mine)

    assigned = client.post(
        f"{API}/tickets/{ticket['id']}/assign",
        json={"assignee_id": agent_id},
        headers=auth(tokens["admin"]),
    )
    assert assigned.status_code == 200, assigned.text

    # After assignment the tabs swap.
    mine = client.get(
        f"{API}/tickets?assignee_id={agent_id}&limit=100", headers=auth(tokens["admin"])
    )
    assert ticket["id"] in _ids(mine)
    unassigned = client.get(
        f"{API}/tickets?unassigned=true&limit=100", headers=auth(tokens["admin"])
    )
    assert ticket["id"] not in _ids(unassigned)


def test_a_queue_filter_cannot_widen_a_requesters_row_scope(client, tokens, db):
    """The filter narrows; `scope_tickets_to_caller` still decides the ceiling."""
    other = make_ticket(client, tokens["requester"])
    directory = client.get(f"{API}/users", headers=auth(tokens["admin"])).json()
    requester_id = next(u["id"] for u in directory if u["email"] == "requester@agentdesk.dev")

    # A second requester asking for the first one's tickets gets nothing back.
    from tests.helpers.factories import verified_requester

    stranger = verified_requester(client, db)
    response = client.get(
        f"{API}/tickets?assignee_id={requester_id}&limit=100", headers=auth(stranger["token"])
    )
    assert response.status_code == 200
    assert other["id"] not in _ids(response)


# --- Staff directory (assignment modal + @mention autocomplete) ---


def test_an_agent_may_read_the_staff_directory(client, tokens):
    response = client.get(f"{API}/users", headers=auth(tokens["agent"]))
    assert response.status_code == 200, response.text
    assert response.json(), "an agent needs colleagues to assign to and mention"


def test_a_requester_may_not_read_the_directory(client, tokens):
    assert client.get(f"{API}/users", headers=auth(tokens["requester"])).status_code == 403


# --- Knowledge base creation loop (App Flow §19) ---


def _draft(client, token, **overrides) -> dict:
    body = {"title": f"KB {rand()}", "body": f"Resolution steps {rand()}", **overrides}
    return client.post(f"{API}/knowledge-base/articles", json=body, headers=auth(token))


def test_an_agent_drafts_an_article_from_a_resolved_ticket(client, tokens):
    ticket = make_ticket(client, tokens["requester"])
    response = _draft(client, tokens["agent"], source_ticket_id=ticket["id"])
    assert response.status_code == 201, response.text
    article = response.json()
    assert article["status"] == "draft"
    assert article["published_at"] is None
    assert article["source_ticket_id"] == ticket["id"]


def test_an_agent_may_not_publish(client, tokens):
    """§19 steps 4–5: review and publication are the Admin's, not the author's."""
    assert _draft(client, tokens["agent"], status="published").status_code == 403

    article = _draft(client, tokens["agent"]).json()
    patched = client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"status": "published"},
        headers=auth(tokens["agent"]),
    )
    assert patched.status_code == 403


def test_an_admin_publishes_the_draft_and_it_becomes_requester_visible(client, tokens):
    article = _draft(client, tokens["agent"]).json()

    # Still invisible to a requester while it is a draft.
    hidden = client.get(
        f"{API}/knowledge-base/articles/{article['id']}", headers=auth(tokens["requester"])
    )
    assert hidden.status_code == 404

    published = client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"status": "published"},
        headers=auth(tokens["admin"]),
    )
    assert published.status_code == 200, published.text
    assert published.json()["published_at"] is not None

    visible = client.get(
        f"{API}/knowledge-base/articles/{article['id']}", headers=auth(tokens["requester"])
    )
    assert visible.status_code == 200


def test_only_the_author_or_an_admin_may_edit_a_draft(client, tokens):
    article = _draft(client, tokens["agent"]).json()
    response = client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"body": "Rewritten by someone else"},
        headers=auth(tokens["team_lead"]),
    )
    # The lead cannot even see another agent's draft, so it reads as absent.
    assert response.status_code in (403, 404)

    own = client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"body": "Rewritten by the author"},
        headers=auth(tokens["agent"]),
    )
    assert own.status_code == 200, own.text
    assert own.json()["body"] == "Rewritten by the author"


@pytest.mark.parametrize("method,path", [("post", ""), ("patch", "/{id}")])
def test_a_requester_may_not_write_articles(client, tokens, method, path):
    article = _draft(client, tokens["admin"]).json()
    url = f"{API}/knowledge-base/articles{path.format(id=article['id'])}"
    response = getattr(client, method)(
        url, json={"title": "x", "body": "y"}, headers=auth(tokens["requester"])
    )
    assert response.status_code == 403


def test_writing_an_article_lands_in_the_audit_log(client, tokens, db):
    import sqlalchemy as sa

    article = _draft(client, tokens["agent"]).json()
    with db.connect() as conn:
        actions = (
            conn.execute(
                sa.text(
                    "SELECT action FROM audit_logs WHERE entity_type = 'knowledge_base_article' "
                    "AND entity_id = :id"
                ),
                {"id": article["id"]},
            )
            .scalars()
            .all()
        )
    assert "created" in actions


# --- Phase 14 checkpoint: the loop closes (App Flow §19 steps 5–6) ---


def test_publishing_embeds_the_article_so_it_can_be_suggested(client, tokens, db, monkeypatch):
    """Without a vector the AI pipeline's retrieval node skips the article
    entirely (`embedding IS NOT NULL`), so publishing must generate one."""

    from app.knowledge_base import service as kb

    async def fake_embed(text: str) -> list[float]:
        assert "Reindex me" in text, "the embedding must cover the title, not just the body"
        return [0.1] * EMBEDDING_DIM

    monkeypatch.setattr(kb.gemini, "embed", fake_embed)

    article = _draft(client, tokens["agent"], title=f"Reindex me {rand()}").json()
    assert _embedding_of(db, article["id"]) is None, "a draft is not suggestible yet"

    published = client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"status": "published"},
        headers=auth(tokens["admin"]),
    )
    assert published.status_code == 200, published.text
    assert _embedding_of(db, article["id"]) is not None


def test_publishing_survives_an_embedding_failure(client, tokens, monkeypatch):
    """The provider being down must not block review — §19 step 5 is a human
    decision, and the article is still findable by full-text search."""
    from app.knowledge_base import service as kb

    async def boom(_text: str) -> list[float]:
        raise RuntimeError("provider down")

    monkeypatch.setattr(kb.gemini, "embed", boom)
    article = _draft(client, tokens["agent"]).json()
    published = client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"status": "published"},
        headers=auth(tokens["admin"]),
    )
    assert published.status_code == 200, published.text


def test_editing_a_published_article_refreshes_its_embedding(client, tokens, db, monkeypatch):
    from app.knowledge_base import service as kb

    async def fake_embed(text: str) -> list[float]:
        return [0.2 if "Rewritten" in text else 0.1] * EMBEDDING_DIM

    monkeypatch.setattr(kb.gemini, "embed", fake_embed)
    article = _draft(client, tokens["admin"], status="published").json()
    before = _embedding_of(db, article["id"])

    client.patch(
        f"{API}/knowledge-base/articles/{article['id']}",
        json={"body": "Rewritten guidance"},
        headers=auth(tokens["admin"]),
    )
    assert _embedding_of(db, article["id"]) != before, "a stale vector matches the wrong tickets"


def test_a_draft_never_reaches_a_requester_through_search(client, tokens):
    """Checkpoint: unpublished work is invisible in browse, global search and
    the chat widget's suggestions alike — all three share one scope."""
    marker = rand("secret")
    _draft(client, tokens["agent"], title=f"Draft {marker}", body=f"Secret {marker}")

    browse = client.get(
        f"{API}/knowledge-base/articles", params={"q": marker}, headers=auth(tokens["requester"])
    )
    assert marker not in str(browse.json())

    found = client.get(
        f"{API}/search/tickets", params={"q": marker}, headers=auth(tokens["requester"])
    )
    assert found.status_code == 200, found.text
    assert marker not in str(found.json()["kb_articles"])


def test_search_does_not_leak_another_agents_draft(client, tokens):
    """`/search` reuses `scope_articles_to_caller`, so a lead sees published
    articles plus their own drafts — never a colleague's."""
    marker = rand("private")
    _draft(client, tokens["agent"], title=f"Draft {marker}", body=f"Notes {marker}")

    for token in (tokens["team_lead"], tokens["agent"]):
        hits = client.get(f"{API}/search/tickets", params={"q": marker}, headers=auth(token)).json()
        titles = {a["title"] for a in hits["kb_articles"]}
        assert (f"Draft {marker}" in titles) == (token is tokens["agent"])


def test_the_admin_review_queue_filters_to_drafts(client, tokens):
    """§19 step 4: the Admin needs to find what is waiting for review."""
    marker = rand("review")
    _draft(client, tokens["agent"], title=f"Draft {marker}")
    _draft(client, tokens["admin"], title=f"Live {marker}", status="published")

    drafts = client.get(
        f"{API}/knowledge-base/articles",
        params={"q": marker, "status": "draft"},
        headers=auth(tokens["admin"]),
    )
    assert drafts.status_code == 200, drafts.text
    titles = {a["title"] for a in drafts.json()}
    assert f"Draft {marker}" in titles
    assert f"Live {marker}" not in titles, "the review queue is drafts only"


def _embedding_of(db, article_id: str):
    import sqlalchemy as sa

    with db.connect() as conn:
        return conn.execute(
            sa.text("SELECT embedding FROM knowledge_base_articles WHERE id = :id"),
            {"id": article_id},
        ).scalar()
