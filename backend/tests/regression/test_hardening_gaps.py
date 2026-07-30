"""Missing validation at trust boundaries.

Lower severity than the crash and integrity defects: none of these is currently
exploitable into a data breach on its own. They are the checks a reviewer would
expect to find, whose absence widens the blast radius of anything else.
"""

import pytest
import sqlalchemy as sa

from tests.helpers import factories as f
from tests.helpers.auth import API, auth

# Every Medium and Low gap in this file is fixed (BUG-20 resolved as a schema
# decision — see Doc 05). What is left open is the two Informational items.
open_gap = pytest.mark.xfail(strict=True, reason="confirmed gap — see TEST_REPORT.md")


def test_an_uploaded_files_declared_mime_type_is_verified_against_its_bytes(client, tokens):
    """BUG-13 (Medium): the MIME allow-list trusts a client-supplied header.

    `_mime_allowed` checks `UploadFile.content_type`, which is whatever the
    client wrote in the multipart part header. Renaming a Windows executable to
    `.png` and declaring `image/png` sails through the allow-list, and the bytes
    land on disk under the storage root.

    The download path sets `Content-Disposition: attachment` and serves the
    declared type, so this is not directly stored XSS — it is an arbitrary-file
    store that the allow-list is supposed to prevent, and a staging point for
    anything downstream that trusts the extension.

    Fix: sniff the leading bytes before writing. `filetype`/`python-magic` is
    the thorough option; for the documented set, a small prefix table
    (`\\x89PNG`, `\\xff\\xd8\\xff`, `%PDF`, `PK\\x03\\x04`) checked against the
    declared type in `add_attachment` covers it without a new dependency.
    """
    ticket = f.make_ticket(client, tokens["requester"])
    windows_executable = b"MZ\x90\x00\x03" + b"\x00" * 200

    response = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": ("holiday-photo.png", windows_executable, "image/png")},
        headers=auth(tokens["requester"]),
    )
    assert response.status_code == 415, (
        f"an executable declared as image/png was accepted ({response.status_code})"
    )


def test_an_empty_file_is_rejected(client, tokens):
    """BUG-14 (Low): a zero-byte upload creates an attachment row and a file.

    `add_attachment` never checks the lower bound, so an empty part produces a
    `size_bytes = 0` row and an empty file on disk. Harmless individually;
    a cheap way to inflate storage and clutter a ticket in bulk.

    Fix: one guard beside the existing size-cap check.
    """
    ticket = f.make_ticket(client, tokens["requester"])
    response = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": ("empty.png", b"", "image/png")},
        headers=auth(tokens["requester"]),
    )
    assert response.status_code == 422, f"a zero-byte upload was accepted ({response.status_code})"


@pytest.mark.parametrize("field", ["subject", "description"])
def test_ticket_text_fields_have_an_upper_length_bound(client, tokens, field):
    """BUG-15 (Low): free-text fields have a minimum length but no maximum.

    `TicketCreate` sets `min_length=1` on subject and description and no cap, so
    a single request can store a megabyte per field. Postgres `text` will hold
    it, the FTS GIN index will try to tokenise it, and every list response that
    includes the ticket carries it in full.

    Fix: add `max_length` to the schema fields — the UI already truncates, so
    something like 200 for subject and 20000 for description matches reality.
    """
    body = {"subject": "s", "description": "d", "channel": "portal"}
    body[field] = "x" * 100_000
    response = client.post(f"{API}/tickets", json=body, headers=auth(tokens["requester"]))
    assert response.status_code == 422, (
        f"a 100,000-character {field} was accepted ({response.status_code})"
    )


def test_comment_bodies_have_an_upper_length_bound(client, tokens):
    """BUG-15b (Low): the same gap on `CommentCreate.body`."""
    ticket = f.make_ticket(client, tokens["requester"])
    response = f.comment(client, tokens["requester"], ticket["id"], "x" * 1_000_000)
    assert response.status_code == 422, f"a 1MB comment body was accepted ({response.status_code})"


def test_an_automation_rules_actions_are_validated_when_it_is_created(client, tokens):
    """BUG-16 (Low): rule actions are only validated at execution time.

    `_validate_rule` checks `trigger_type` and each condition's `field`, but
    never looks at `actions`. A rule with `{"type": "rm -rf"}` is accepted with
    a 201, then raises `ValueError: Unknown action type` on every single ticket
    that matches it — one `automation_execution_logs` row with status `failed`
    per ticket, forever, with no signal to the admin who created it.

    Worse for operations: once it has execution history it can no longer be
    deleted (`DELETE` returns 409 by design), so a typo is permanent clutter.

    Fix: validate action `type` against the same vocabulary `_execute_actions`
    dispatches on, in `_validate_rule`, alongside the condition-field check.
    """
    response = client.post(
        f"{API}/admin/automation-rules",
        json={
            "name": f.rand("bad-action-"),
            "trigger_type": "ticket_created",
            "conditions": [],
            "actions": [{"type": "definitely_not_an_action"}],
        },
        headers=auth(tokens["admin"]),
    )
    if response.status_code == 201:  # clean up the rule the API should have refused
        f.delete_rule(client, tokens["admin"], response.json()["id"])
    assert response.status_code == 422, (
        f"a rule with an unknown action type was accepted ({response.status_code})"
    )


def test_a_webhook_target_cannot_point_at_a_link_local_address(client, tokens):
    """BUG-17 (Low): webhook targets are not validated, allowing SSRF.

    `target_url` goes straight into `httpx.post` from a background task with no
    scheme or host restriction. An admin can register
    `http://169.254.169.254/latest/meta-data/` (cloud instance metadata),
    `http://localhost:5432`, or a `file://`-adjacent internal service, and the
    application will POST signed ticket payloads to it on every matching event.

    Admin-only, so this is a privilege-boundary hardening gap rather than a
    privilege escalation — but the whole point of an SSRF control is that the
    request originates from inside the network perimeter, which an admin's own
    browser does not.

    Fix: validate in `create_webhook` — require https (or http only outside
    production), resolve the host, and reject loopback, link-local, and private
    ranges via `ipaddress.ip_address(...).is_private / is_link_local`.
    """
    created = client.post(
        f"{API}/webhooks",
        json={
            "event_type": "ticket_created",
            "target_url": "http://169.254.169.254/latest/meta-data/",
        },
        headers=auth(tokens["admin"]),
    )
    if created.status_code == 201:
        client.delete(f"{API}/webhooks/{created.json()['id']}", headers=auth(tokens["admin"]))
    assert created.status_code == 422, (
        f"a link-local webhook target was accepted ({created.status_code})"
    )


@open_gap
def test_an_unknown_status_filter_is_rejected_rather_than_silently_empty(client, tokens):
    """BUG-18 (Informational): `GET /tickets?status=nonsense` returns 200 [].

    The filter is passed through to the WHERE clause unvalidated, so a typo or a
    renamed status is indistinguishable from a genuinely empty result. A client
    cannot tell "no tickets are on hold" from "on_hold is not a status".

    Fix: validate `status` against `engine.STATUSES` in the router, returning
    422 for anything outside it.
    """
    response = client.get(
        f"{API}/tickets",
        params={"status": "definitely_not_a_status"},
        headers=auth(tokens["admin"]),
    )
    assert response.status_code == 422, (
        f"an unknown status filter returned {response.status_code}, not 422"
    )


@open_gap
def test_the_in_memory_report_store_does_not_grow_without_bound(client, tokens):
    """BUG-19 (Informational): generated reports are never evicted.

    `app/reporting/service._REPORTS` is a module-level dict that only ever
    grows — every `POST /reports/generate` adds an entry holding the full row
    set, and nothing removes it. A long-running process accumulates every report
    any user has ever generated.

    The module already flags the store as prototype-only; this test pins the
    consequence so it is not forgotten when the store becomes durable.

    Fix: cap it. An `OrderedDict` with a size limit, or a timestamp sweep on
    insert, is a few lines and needs no new dependency.
    """
    from app.reporting import service as reporting

    before = len(reporting._REPORTS)
    for _ in range(25):
        client.post(
            f"{API}/reports/generate",
            json={"report_type": "ticket_trends"},
            headers=auth(tokens["agent"]),
        )
    growth = len(reporting._REPORTS) - before
    assert growth < 25, f"the report store grew by {growth} with no eviction"


def test_deleting_a_comment_leaves_the_body_in_the_audit_trail(client, db, tokens):
    """BUG-20 (Low): resolved as a schema decision — hard deletion is intended.

    Comments are the one destructive path that does not soft-delete;
    `attachments.deleted_at` exists, `comments.deleted_at` deliberately does not
    (Doc 05, `comments`). The row goes for real, and the `audit_logs` row is the
    surviving record — so what has to hold is that the body is *in* that row.
    If someone ever "tidies" `before_state` out of `delete_comment`, the delete
    becomes unrecoverable and this fails.
    """
    ticket = f.make_ticket(client, tokens["requester"])
    body = f"to delete {f.rand()}"
    created = f.comment(client, tokens["requester"], ticket["id"], body)
    comment_id = created.json()["id"]

    assert (
        client.delete(f"{API}/comments/{comment_id}", headers=auth(tokens["requester"])).status_code
        == 204
    )

    with db.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT count(*) FROM comments WHERE id = :c"), {"c": comment_id}
            ).scalar_one()
            == 0
        ), "the comment row survived a delete Doc 05 documents as hard"
        audited = conn.execute(
            sa.text(
                "SELECT before_state->>'body' FROM audit_logs "
                "WHERE entity_type = 'comment' AND entity_id = :c AND action = 'deleted'"
            ),
            {"c": comment_id},
        ).scalar_one()
    assert audited == body, "the audit row is the only surviving copy and it lost the body"


def test_the_notify_actions_message_reaches_the_recipient(client, db, tokens, user_ids):
    """BUG-23 (Low): an automation rule's `notify` message is silently discarded.

    `notifications.notify` treats the caller's subject/message as a *fallback*
    used only when no active template exists for the (trigger, channel) pair.
    `scripts/seed.py` writes a default template for every pair, including
    `automation_executed` — so in any seeded deployment the template always wins
    and the `message` an admin typed into the rule builder never appears.

    Nothing errors and the notification is delivered, so the only symptom is an
    admin wondering why their custom text is ignored.

    Fix: give the caller precedence for this one trigger, or drop `message` from
    the action schema and document that `automation_executed` copy is edited
    through the notification template instead. The second is smaller and matches
    how every other trigger already works.
    """
    import sqlalchemy as sa

    marker = f.rand("notify-msg-")
    rule = f.make_rule(
        client,
        tokens["admin"],
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=[
            {"type": "notify", "user_id": user_ids["agent"], "message": "Bespoke rule message"}
        ],
    )
    try:
        ticket = f.make_ticket(client, tokens["requester"], subject=f"{marker} trigger")
        with db.connect() as conn:
            payload = conn.execute(
                sa.text(
                    "SELECT payload FROM notifications WHERE ticket_id = :t "
                    "AND trigger_type = 'automation_executed' AND channel = 'in_app' LIMIT 1"
                ),
                {"t": ticket["id"]},
            ).scalar_one()
        assert payload["message"] == "Bespoke rule message", (
            f"the rule's message was replaced by the template: {payload['message']!r}"
        )
    finally:
        f.delete_rule(client, tokens["admin"], rule["id"])
