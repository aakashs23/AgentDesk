"""The API surface the Customer Portal (Phase 10) needs: taxonomy reads, the
knowledge base read API, CSAT responses, and authenticated password change.

Each of these was listed in `test_api_surface.MISSING_ENDPOINTS` until Phase 10;
these are the "real tests" that file asks for when a gap gets filled.
"""

import uuid

import pytest
import sqlalchemy as sa

from tests.helpers.auth import API, ROLES, auth, login, token_for
from tests.helpers.factories import drive_to, make_ticket, rand, verified_requester

# --- Taxonomy reads (Doc 05 §6: read-only for every role "where exposed") ---


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("path", ["/categories", "/priorities"])
def test_every_role_can_read_taxonomy(client, tokens, role, path):
    response = client.get(f"{API}{path}", headers=auth(tokens[role]))
    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


@pytest.mark.parametrize("path", ["/categories", "/priorities"])
def test_taxonomy_requires_authentication(client, path):
    assert client.get(f"{API}{path}").status_code == 401


def test_categories_expose_the_parent_link_the_tree_needs(client, tokens):
    response = client.get(f"{API}/categories", headers=auth(tokens["requester"]))
    categories = response.json()
    assert categories, "seed data should provide a category tree"
    assert {"id", "name", "parent_id"} <= set(categories[0])
    # The seed builds a two-level tree; without at least one child the portal's
    # nesting logic would never be exercised.
    assert any(c["parent_id"] for c in categories)


def test_priorities_come_back_ascending_by_rank(client, tokens):
    priorities = client.get(f"{API}/priorities", headers=auth(tokens["requester"])).json()
    assert priorities
    ranks = [p["rank"] for p in priorities]
    assert ranks == sorted(ranks)
    assert all(p["color_hex"].startswith("#") for p in priorities)


# --- Knowledge base reads (Doc 05 §6 visibility matrix) ---


def _make_article(db, title: str, status: str, author_id=None) -> str:
    article_id = uuid.uuid4()
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO knowledge_base_articles "
                "(id, title, body, status, author_id, published_at, created_at, updated_at) "
                "VALUES (:id, :t, :b, :s, :a, now(), now(), now())"
            ),
            {
                "id": article_id,
                "t": title,
                "b": f"Body of {title}",
                "s": status,
                "a": author_id,
            },
        )
    return str(article_id)


def test_requester_sees_published_articles_but_not_drafts(client, tokens, db):
    marker = rand("kb")
    published = _make_article(db, f"Published {marker}", "published")
    draft = _make_article(db, f"Draft {marker}", "draft")

    listed = client.get(
        f"{API}/knowledge-base/articles", params={"q": marker}, headers=auth(tokens["requester"])
    )
    assert listed.status_code == 200, listed.text
    ids = {a["id"] for a in listed.json()}
    assert published in ids
    assert draft not in ids


def test_requester_fetching_a_draft_gets_404_not_403(client, tokens, db):
    """A 403 would confirm the draft exists — unpublished work stays invisible."""
    draft = _make_article(db, f"Draft {rand('kb')}", "draft")
    response = client.get(
        f"{API}/knowledge-base/articles/{draft}", headers=auth(tokens["requester"])
    )
    assert response.status_code == 404


def test_admin_sees_drafts(client, tokens, db):
    marker = rand("kb")
    draft = _make_article(db, f"Draft {marker}", "draft")
    listed = client.get(
        f"{API}/knowledge-base/articles", params={"q": marker}, headers=auth(tokens["admin"])
    )
    assert draft in {a["id"] for a in listed.json()}
    detail = client.get(f"{API}/knowledge-base/articles/{draft}", headers=auth(tokens["admin"]))
    assert detail.status_code == 200
    assert detail.json()["body"]


def test_article_detail_carries_the_body_and_the_list_does_not(client, tokens, db):
    marker = rand("kb")
    article = _make_article(db, f"Published {marker}", "published")

    listed = client.get(
        f"{API}/knowledge-base/articles", params={"q": marker}, headers=auth(tokens["requester"])
    ).json()
    assert "body" not in listed[0], "list responses stay small; body is detail-only"

    detail = client.get(
        f"{API}/knowledge-base/articles/{article}", headers=auth(tokens["requester"])
    )
    assert detail.status_code == 200
    assert detail.json()["body"] == f"Body of Published {marker}"


def test_kb_search_matches_on_body_not_just_title(client, tokens, db):
    """Browse search is the ranked matcher `/search` uses, so a phrase that only
    appears in the body still finds the article — and it ranks first, rather
    than being the only row a substring match would have allowed."""
    marker = rand("kbbody")
    article = _make_article(db, f"Findable {marker}", "published")
    response = client.get(
        f"{API}/knowledge-base/articles",
        params={"q": f"Body of Findable {marker}"},
        headers=auth(tokens["requester"]),
    )
    assert [a["id"] for a in response.json()][:1] == [article]


def test_kb_requires_authentication(client):
    assert client.get(f"{API}/knowledge-base/articles").status_code == 401


# --- CSAT ---


def _resolved_ticket(client, tokens, db) -> tuple[dict, str]:
    """A ticket owned by a fresh requester, driven to `resolved`.

    Driven as admin, not agent: a brand-new requester's ticket is unassigned and
    in no team queue, so an agent cannot even see it (Doc 05 §6).
    """
    requester = verified_requester(client, db)
    ticket = make_ticket(client, requester["token"])
    drive_to(client, tokens, ticket["id"], "resolved", staff_role="admin")
    return requester, ticket["id"]


def test_requester_rates_their_resolved_ticket(client, tokens, db):
    requester, ticket_id = _resolved_ticket(client, tokens, db)
    response = client.post(
        f"{API}/csat",
        json={"ticket_id": ticket_id, "rating": 5, "comment": "Sorted quickly"},
        headers=auth(requester["token"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rating"] == 5
    assert body["ticket_id"] == ticket_id


def test_a_ticket_can_only_be_rated_once(client, tokens, db):
    requester, ticket_id = _resolved_ticket(client, tokens, db)
    first = client.post(
        f"{API}/csat", json={"ticket_id": ticket_id, "rating": 4}, headers=auth(requester["token"])
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"{API}/csat", json={"ticket_id": ticket_id, "rating": 1}, headers=auth(requester["token"])
    )
    assert second.status_code == 409


def test_an_unresolved_ticket_cannot_be_rated(client, db):
    requester = verified_requester(client, db)
    ticket = make_ticket(client, requester["token"])
    response = client.post(
        f"{API}/csat",
        json={"ticket_id": ticket["id"], "rating": 5},
        headers=auth(requester["token"]),
    )
    assert response.status_code == 409


def test_staff_cannot_rate_a_ticket_on_the_requesters_behalf(client, tokens, db):
    """Uses admin deliberately: admin can see every ticket, so a 403 here proves
    the requester-only rule is enforced on its own rather than falling out of
    ticket visibility (an agent would 404 before ever reaching the check)."""
    _, ticket_id = _resolved_ticket(client, tokens, db)
    response = client.post(
        f"{API}/csat", json={"ticket_id": ticket_id, "rating": 5}, headers=auth(tokens["admin"])
    )
    assert response.status_code == 403


def test_another_requester_cannot_rate_someone_elses_ticket(client, tokens, db):
    _, ticket_id = _resolved_ticket(client, tokens, db)
    outsider = verified_requester(client, db)
    response = client.post(
        f"{API}/csat", json={"ticket_id": ticket_id, "rating": 1}, headers=auth(outsider["token"])
    )
    # 404, not 403 — the ticket scoping must not leak that it exists.
    assert response.status_code == 404


@pytest.mark.parametrize("rating", [0, 6, -1])
def test_rating_must_be_within_one_to_five(client, tokens, db, rating):
    requester, ticket_id = _resolved_ticket(client, tokens, db)
    response = client.post(
        f"{API}/csat",
        json={"ticket_id": ticket_id, "rating": rating},
        headers=auth(requester["token"]),
    )
    assert response.status_code == 422


def test_get_csat_by_ticket_tells_the_portal_whether_to_show_the_survey(client, tokens, db):
    requester, ticket_id = _resolved_ticket(client, tokens, db)

    before = client.get(
        f"{API}/csat", params={"ticket_id": ticket_id}, headers=auth(requester["token"])
    )
    assert before.status_code == 200
    assert before.json() == []

    client.post(
        f"{API}/csat", json={"ticket_id": ticket_id, "rating": 3}, headers=auth(requester["token"])
    )
    after = client.get(
        f"{API}/csat", params={"ticket_id": ticket_id}, headers=auth(requester["token"])
    )
    assert len(after.json()) == 1


def test_csat_list_is_scoped_to_tickets_the_caller_can_see(client, tokens, db):
    requester, ticket_id = _resolved_ticket(client, tokens, db)
    client.post(
        f"{API}/csat", json={"ticket_id": ticket_id, "rating": 5}, headers=auth(requester["token"])
    )
    outsider = verified_requester(client, db)
    visible = client.get(f"{API}/csat", headers=auth(outsider["token"])).json()
    assert all(r["ticket_id"] != ticket_id for r in visible)


# --- Attachment listing (the portal's Attachments tab) ---


def test_ticket_attachments_can_be_listed(client, db):
    requester = verified_requester(client, db)
    ticket = make_ticket(client, requester["token"])

    empty = client.get(
        f"{API}/tickets/{ticket['id']}/attachments", headers=auth(requester["token"])
    )
    assert empty.status_code == 200
    assert empty.json() == []

    upload = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": ("note.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=auth(requester["token"]),
    )
    assert upload.status_code == 201, upload.text

    listed = client.get(
        f"{API}/tickets/{ticket['id']}/attachments", headers=auth(requester["token"])
    )
    assert [a["file_name"] for a in listed.json()] == ["note.pdf"]


def test_attachment_listing_is_scoped_to_the_ticket_owner(client, db):
    requester = verified_requester(client, db)
    ticket = make_ticket(client, requester["token"])
    outsider = verified_requester(client, db)

    response = client.get(
        f"{API}/tickets/{ticket['id']}/attachments", headers=auth(outsider["token"])
    )
    assert response.status_code == 404


# --- Authenticated password change ---


def test_password_change_updates_the_password(client, db):
    requester = verified_requester(client, db)
    new_password = "BrandNewPass456!"

    response = client.post(
        f"{API}/auth/password-change",
        json={"current_password": requester["password"], "new_password": new_password},
        headers=auth(requester["token"]),
    )
    assert response.status_code == 200, response.text

    assert login(client, requester["email"], requester["password"]).status_code == 401
    assert token_for(client, requester["email"], new_password)


def test_password_change_rejects_a_wrong_current_password(client, db):
    requester = verified_requester(client, db)
    response = client.post(
        f"{API}/auth/password-change",
        json={"current_password": "NotMyPassword1!", "new_password": "BrandNewPass456!"},
        headers=auth(requester["token"]),
    )
    assert response.status_code == 400
    # The original password still works — nothing was changed.
    assert token_for(client, requester["email"], requester["password"])


def test_password_change_revokes_other_sessions(client, db):
    """TRD §9: a password change must not leave a stolen refresh token usable."""
    requester = verified_requester(client, db)
    stale_refresh = client.post(
        f"{API}/auth/login",
        json={"email": requester["email"], "password": requester["password"]},
    ).json()["refresh_token"]

    client.post(
        f"{API}/auth/password-change",
        json={"current_password": requester["password"], "new_password": "BrandNewPass456!"},
        headers=auth(requester["token"]),
    )

    replay = client.post(f"{API}/auth/refresh", json={"refresh_token": stale_refresh})
    assert replay.status_code == 401


def test_password_change_requires_authentication(client):
    response = client.post(
        f"{API}/auth/password-change",
        json={"current_password": "x", "new_password": "BrandNewPass456!"},
    )
    assert response.status_code == 401
