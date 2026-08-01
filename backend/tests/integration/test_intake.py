"""Multi-channel intake — email-to-ticket and the chat widget (Phase 13).

Covers the Implementation Plan's three Phase 13 checkpoints directly: a test
email creates a classified ticket and its reply appends rather than duplicates;
a malformed email lands in the manual review queue; an unresolved chat converts
into a ticket carrying the whole transcript.
"""

from email.message import EmailMessage

import pytest
import sqlalchemy as sa

from app.config import get_settings
from app.intake import parser
from app.intake.email_service import MANUAL_REVIEW_QUEUE
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth
from tests.helpers.factories import rand, verified_requester

TOKEN = "test-inbound-token"


@pytest.fixture(autouse=True)
def inbound_token():
    """The route is disabled without a shared secret, which is itself a test."""
    settings = get_settings()
    previous = settings.inbound_email_token
    settings.inbound_email_token = TOKEN
    yield TOKEN
    settings.inbound_email_token = previous


def raw_email(
    sender: str,
    subject: str,
    body: str,
    message_id: str | None = None,
    in_reply_to: str | None = None,
    attachment: tuple[str, str, bytes] | None = None,
) -> str:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "support@agentdesk.local"
    message["Subject"] = subject
    message["Message-ID"] = message_id or f"<{rand('m')}@example.com>"
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    message.set_content(body)
    if attachment:
        name, mime, content = attachment
        maintype, _, subtype = mime.partition("/")
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
    return message.as_string()


def post_email(client, raw: str, token: str = TOKEN):
    return client.post(f"{API}/intake/email", json={"raw": raw}, headers={"X-Inbound-Token": token})


# --- Parser (pure; App Flow §11 steps 3–4) ---


def test_the_parser_extracts_sender_subject_and_body():
    parsed = parser.parse(
        raw_email("Dana Scully <dana@example.com>", "Printer down", "It jams.").encode()
    )
    assert parsed.problem is None
    assert parsed.sender_email == "dana@example.com"
    assert parsed.sender_name == "Dana Scully"
    assert parsed.subject == "Printer down"
    assert "It jams." in parsed.body


def test_the_parser_flags_a_message_with_no_sender_or_no_body():
    assert parser.parse(b"Subject: hi\n\nbody").problem == "no usable sender address"
    assert parser.parse(raw_email("a@example.com", "Subject only", "   ").encode()).problem == (
        "empty or unreadable body"
    )


def test_reply_matching_keys_survive_mail_client_mangling():
    assert parser.display_id_in("Re: [AGT-42] Printer down") == 42
    assert parser.display_id_in("Printer down") is None
    # Subject normalisation is what the sender+subject fallback compares on.
    assert parser.normalise_subject("Re: Fwd: [AGT-42] Printer Down ") == "printer down"
    assert parser.normalise_subject("printer down") == "printer down"
    # Only the new text survives, not the quoted history it was written above.
    assert parser.strip_quoted("Still broken.\n\nOn Tue, X wrote:\n> original") == "Still broken."
    # ...unless quoting is all there is, which beats storing an empty comment.
    assert parser.strip_quoted("> only quoted text") == "> only quoted text"


# --- Email intake (App Flow §11) ---


def test_the_inbound_route_is_shut_without_the_shared_secret(client):
    settings = get_settings()
    settings.inbound_email_token = ""
    try:
        assert_status(post_email(client, raw_email("a@example.com", "x", "y")), 503)
    finally:
        settings.inbound_email_token = TOKEN
    assert_status(post_email(client, raw_email("a@example.com", "x", "y"), token="wrong"), 401)


def test_an_email_creates_a_ticket_and_acknowledges_it_with_the_ref(client, db, outbox, tokens):
    sender = f"emailer-{rand()}@example.com"
    subject = f"VPN drops every hour {rand()}"
    response = post_email(client, raw_email(sender, subject, "It disconnects at :00."))
    assert_status(response, 202)
    assert response.json()["action"] == "created"

    with db.connect() as conn:
        display_id, description = conn.execute(
            sa.text("SELECT display_id, description FROM tickets WHERE subject = :s"),
            {"s": subject},
        ).one()
    assert "disconnects" in description

    # §11 step 8: the ack carries the ref future replies are matched on.
    acks = [mail for mail in outbox if mail[0] == sender]
    assert acks, f"no acknowledgment sent to {sender}"
    assert f"[AGT-{display_id}]" in acks[-1][1]

    # The sender had no account; §11 requires the ticket to exist anyway.
    with db.connect() as conn:
        assert conn.execute(sa.text("SELECT 1 FROM users WHERE email = :e"), {"e": sender}).first()


def test_replying_to_the_acknowledgment_appends_instead_of_duplicating(client, db, outbox, tokens):
    sender = f"emailer-{rand()}@example.com"
    subject = f"Laptop will not boot {rand()}"
    assert_status(post_email(client, raw_email(sender, subject, "Black screen.")), 202)
    with db.connect() as conn:
        ticket_id, display_id = conn.execute(
            sa.text("SELECT id, display_id FROM tickets WHERE subject = :s"), {"s": subject}
        ).one()

    reply = post_email(
        client, raw_email(sender, f"Re: [AGT-{display_id}] {subject}", "Now it beeps twice.")
    )
    assert_status(reply, 202)
    assert reply.json()["action"] == "appended"

    with db.connect() as conn:
        tickets = conn.execute(
            sa.text("SELECT count(*) FROM tickets WHERE subject LIKE :s"), {"s": f"%{subject}%"}
        ).scalar_one()
        bodies = (
            conn.execute(
                sa.text("SELECT body FROM comments WHERE ticket_id = :t"), {"t": ticket_id}
            )
            .scalars()
            .all()
        )
    assert tickets == 1, "the reply created a second ticket"
    assert any("beeps twice" in body for body in bodies)


def test_a_reply_with_no_ref_still_matches_on_sender_and_subject(client, db):
    """§11 step 6's last-resort heuristic — a mail client that strips the tag."""
    sender = f"emailer-{rand()}@example.com"
    subject = f"Badge reader offline {rand()}"
    assert_status(post_email(client, raw_email(sender, subject, "Door 3 is dead.")), 202)
    again = post_email(client, raw_email(sender, f"Re: {subject}", "Door 4 too."))
    assert_status(again, 202)
    assert again.json()["action"] == "appended"


def test_a_malformed_email_lands_in_the_manual_review_queue(client, db):
    """Checkpoint: it neither crashes nor vanishes."""
    response = post_email(client, "Subject: totally unparseable\n\nno From header at all\n")
    assert_status(response, 202)
    assert response.json()["action"] == "manual_review"

    with db.connect() as conn:
        queue_name, status, description = conn.execute(
            sa.text(
                "SELECT q.name, t.status, t.description FROM tickets t "
                "JOIN queues q ON q.id = t.queue_id WHERE t.id = :id"
            ),
            {"id": response.json()["ticket_id"]},
        ).one()
    assert queue_name == MANUAL_REVIEW_QUEUE
    assert status == "new"
    assert "no usable sender address" in description


def test_the_same_message_delivered_twice_files_once(client):
    """A provider retry or a re-polled mailbox must not double-file."""
    sender = f"emailer-{rand()}@example.com"
    message_id = f"<{rand('dup')}@example.com>"
    raw = raw_email(sender, f"Duplicate check {rand()}", "Only once.", message_id=message_id)
    assert post_email(client, raw).json()["action"] == "created"
    assert post_email(client, raw).json()["action"] == "duplicate"


def test_an_email_attachment_lands_on_the_ticket(client, db):
    sender = f"emailer-{rand()}@example.com"
    subject = f"Screenshot attached {rand()}"
    png = bytes.fromhex("89504e470d0a1a0a") + b"fake png body"
    assert_status(
        post_email(
            client,
            raw_email(sender, subject, "See attached.", attachment=("shot.png", "image/png", png)),
        ),
        202,
    )
    with db.connect() as conn:
        names = (
            conn.execute(
                sa.text(
                    "SELECT a.file_name FROM attachments a JOIN tickets t ON t.id = a.ticket_id "
                    "WHERE t.subject = :s"
                ),
                {"s": subject},
            )
            .scalars()
            .all()
        )
    assert names == ["shot.png"]


# --- Chat widget (App Flow §12) ---


def start_chat(client, token) -> str:
    response = client.post(f"{API}/chat/sessions", headers=auth(token))
    assert_status(response, 201)
    body = response.json()
    assert body["messages"][0]["speaker"] == "bot", "the widget must greet first (§12 step 2)"
    return body["session_id"]


def say(client, token, session_id, message):
    return client.post(
        f"{API}/chat/sessions/{session_id}/messages",
        json={"message": message},
        headers=auth(token),
    )


def test_the_bot_answers_every_requester_message(client, tokens):
    session_id = start_chat(client, tokens["requester"])
    response = say(client, tokens["requester"], session_id, "My VPN keeps dropping")
    assert_status(response, 200)
    speakers = [m["speaker"] for m in response.json()["messages"]]
    assert speakers == ["user", "bot"]


def test_an_empty_knowledge_base_does_not_silence_the_bot(client, tokens, monkeypatch):
    """Regression: the bot used to short-circuit to a canned "no article" line
    whenever retrieval came back empty, so a deployment with no published
    articles answered every message identically. §12 step 2 is a conversation —
    nothing to *cite* is not nothing to say."""
    from app.intake import chat_service

    monkeypatch.setattr(get_settings(), "gemini_api_key", "fake-key")
    monkeypatch.setattr(chat_service.search, "embed_query", _none)
    monkeypatch.setattr(chat_service.search, "search_kb", _no_hits)
    monkeypatch.setattr(chat_service.gemini, "generate_text", _fake_llm)

    session_id = start_chat(client, tokens["requester"])
    response = say(client, tokens["requester"], session_id, "My laptop is on fire")
    assert_status(response, 200)
    reply = response.json()["messages"][-1]
    assert reply["speaker"] == "bot"
    assert reply["message"] != chat_service.NO_MATCH


async def _none(_q):
    return None


async def _no_hits(*_args, **_kwargs):
    return []


async def _fake_llm(prompt: str) -> str:
    assert "no matching articles" in prompt, "the model was not told the KB came back empty"
    return "Which model of laptop is it?"


def test_a_resolved_chat_is_a_deflection_and_raises_no_ticket(client, db, tokens):
    session_id = start_chat(client, tokens["requester"])
    assert_status(say(client, tokens["requester"], session_id, f"Password help {rand()}"), 200)
    response = client.post(
        f"{API}/chat/sessions/{session_id}/end",
        json={"resolved": True},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 200)
    assert response.json() is None
    with db.connect() as conn:
        linked = conn.execute(
            sa.text(
                "SELECT count(*) FROM conversation_history "
                "WHERE session_id = :s AND ticket_id IS NOT NULL"
            ),
            {"s": session_id},
        ).scalar_one()
    assert linked == 0


def test_an_unresolved_chat_converts_with_the_whole_transcript(client, db, tokens):
    """Checkpoint: the agent never has to ask the requester to repeat themselves."""
    session_id = start_chat(client, tokens["requester"])
    first = f"Outlook will not sync {rand()}"
    assert_status(say(client, tokens["requester"], session_id, first), 200)
    assert_status(say(client, tokens["requester"], session_id, "Tried restarting, no luck."), 200)

    response = client.post(
        f"{API}/chat/sessions/{session_id}/end",
        json={"resolved": False},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 200)
    ticket = response.json()
    assert ticket["channel"] == "chat"
    assert ticket["subject"] == first
    assert "Tried restarting" in ticket["description"]

    with db.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT speaker, ticket_id FROM conversation_history WHERE session_id = :s"),
            {"s": session_id},
        ).all()
    assert rows, "the transcript vanished"
    assert all(str(ticket_id) == ticket["id"] for _speaker, ticket_id in rows)

    # A converted conversation is closed for further chat.
    assert_status(say(client, tokens["requester"], session_id, "one more thing"), 409)


def test_one_requester_cannot_read_another_requesters_chat(client, db, tokens):
    session_id = start_chat(client, tokens["requester"])
    other = verified_requester(client, db)
    assert_status(
        client.get(f"{API}/chat/sessions/{session_id}", headers=auth(other["token"])), 404
    )
    assert_status(say(client, other["token"], session_id, "let me in"), 404)
    # ...but the owner can.
    assert_status(
        client.get(f"{API}/chat/sessions/{session_id}", headers=auth(tokens["requester"])), 200
    )


def test_an_agent_can_take_over_a_live_chat_and_the_bot_stands_down(client, tokens):
    """§12 step 7."""
    session_id = start_chat(client, tokens["requester"])
    assert_status(say(client, tokens["requester"], session_id, f"Monitor flickers {rand()}"), 200)

    listed = client.get(f"{API}/chat/sessions", headers=auth(tokens["agent"]))
    assert_status(listed, 200)
    assert session_id in [row["session_id"] for row in listed.json()]

    joined = say(client, tokens["agent"], session_id, "Hi, this is Sam — taking a look.")
    assert_status(joined, 200)
    assert [m["speaker"] for m in joined.json()["messages"]] == ["agent"]

    after = say(client, tokens["requester"], session_id, "Thanks!")
    assert_status(after, 200)
    assert [m["speaker"] for m in after.json()["messages"]] == ["user"], (
        "the bot kept talking over the agent who took the conversation"
    )


def test_the_session_list_is_staff_only(client, tokens):
    assert_status(client.get(f"{API}/chat/sessions", headers=auth(tokens["requester"])), 403)
