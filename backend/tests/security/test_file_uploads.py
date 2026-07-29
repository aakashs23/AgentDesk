"""Attachment upload as an attack surface.

Uploads take an attacker-controlled filename, an attacker-controlled MIME type
and attacker-controlled bytes, then write them to disk. Three things must hold:
the filename cannot escape the storage directory, the size cap is enforced
before anything is persisted, and downloads are scoped to callers who can see
the parent ticket.
"""

from pathlib import Path

import pytest
import sqlalchemy as sa

from app.config import get_settings
from tests.helpers import factories as f
from tests.helpers.assertions import assert_hidden, assert_status
from tests.helpers.auth import API, auth

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def ticket(client, tokens):
    return f.make_ticket(client, tokens["requester"])


def _upload(client, token, ticket_id, filename, content=PNG, mime="image/png"):
    return client.post(
        f"{API}/tickets/{ticket_id}/attachments",
        files={"file": (filename, content, mime)},
        headers=auth(token),
    )


# --- Path traversal ---


@pytest.mark.parametrize(
    "filename",
    [
        "../../../../etc/passwd",
        "../../secret.png",
        "....//....//etc/passwd",
        "/etc/passwd",
        "/tmp/pwned.png",
        "..%2f..%2fetc%2fpasswd",
        "./.././.././etc/hosts",
    ],
)
def test_traversal_filenames_cannot_escape_the_storage_directory(
    client, db, tokens, ticket, filename
):
    response = _upload(client, tokens["requester"], ticket["id"], filename)
    assert response.status_code in (201, 415, 422), response.text
    if response.status_code != 201:
        return

    with db.connect() as conn:
        storage_path = conn.execute(
            sa.text("SELECT storage_path FROM attachments WHERE id = :i"),
            {"i": response.json()["id"]},
        ).scalar_one()

    root = Path(get_settings().attachment_dir).resolve()
    written = Path(storage_path).resolve()
    assert written.is_relative_to(root), f"file escaped the storage root: {written}"
    assert written.is_file()
    # And the stored display name carries no directory component either.
    assert "/" not in response.json()["file_name"]


def test_a_traversal_filename_does_not_overwrite_an_existing_file(client, tmp_path, tokens, ticket):
    """Two uploads named the same thing must not collide — the id prefixes them."""
    first = _upload(client, tokens["requester"], ticket["id"], "same.png", b"first" + PNG)
    second = _upload(client, tokens["requester"], ticket["id"], "same.png", b"second" + PNG)
    assert_status(first, 201)
    assert_status(second, 201)
    assert first.json()["id"] != second.json()["id"]

    for response, marker in ((first, b"first"), (second, b"second")):
        downloaded = client.get(
            f"{API}/attachments/{response.json()['id']}", headers=auth(tokens["requester"])
        )
        assert_status(downloaded, 200)
        assert downloaded.content.startswith(marker), "one upload clobbered the other"


@pytest.mark.parametrize("filename", ["", ".", "..", "/", "//", "..."])
def test_degenerate_filenames_do_not_crash_the_upload(client, tokens, ticket, filename):
    response = _upload(client, tokens["requester"], ticket["id"], filename)
    assert response.status_code < 500, f"{filename!r} produced {response.status_code}"


# --- Type and size enforcement ---


@pytest.mark.parametrize(
    "mime",
    [
        "application/x-msdownload",
        "application/x-executable",
        "text/x-shellscript",
        "text/html",
        "application/javascript",
        "application/x-httpd-php",
        "application/zip",
        "application/octet-stream",
    ],
)
def test_disallowed_mime_types_are_rejected(client, tokens, ticket, mime):
    response = _upload(client, tokens["requester"], ticket["id"], "payload.bin", b"MZ\x90", mime)
    assert_status(response, 415, f"mime={mime}")


@pytest.mark.parametrize(
    "mime",
    [
        "image/png",
        "image/jpeg",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ],
)
def test_documented_mime_types_are_accepted(client, tokens, ticket, mime):
    response = _upload(client, tokens["requester"], ticket["id"], "doc.bin", PNG, mime)
    assert_status(response, 201, f"mime={mime}")


def test_an_upload_over_the_cap_is_rejected_and_stores_nothing(client, db, tokens, ticket):
    limit = get_settings().attachment_max_bytes
    oversize = b"\x89PNG" + b"\x00" * (limit + 1024)
    response = _upload(client, tokens["requester"], ticket["id"], "huge.png", oversize)
    assert_status(response, 413, "oversize upload")

    with db.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT count(*) FROM attachments WHERE ticket_id = :t AND size_bytes > :n"),
            {"t": ticket["id"], "n": limit},
        ).scalar_one()
    assert stored == 0, "an over-cap upload was persisted anyway"


def test_an_upload_at_exactly_the_cap_is_accepted(client, tokens, ticket):
    limit = get_settings().attachment_max_bytes
    response = _upload(client, tokens["requester"], ticket["id"], "exact.png", b"\x00" * limit)
    assert_status(response, 201, "upload of exactly the limit")


# --- Access control on stored files ---


def test_attachments_are_only_downloadable_by_callers_who_can_see_the_ticket(client, db, tokens):
    victim = f.verified_requester(client, db)
    victim_ticket = f.make_ticket(client, victim["token"])
    uploaded = _upload(client, victim["token"], victim_ticket["id"], "private.png")
    assert_status(uploaded, 201)

    attacker = f.verified_requester(client, db)
    response = client.get(
        f"{API}/attachments/{uploaded.json()['id']}", headers=auth(attacker["token"])
    )
    assert_hidden(response, "downloaded another requester's attachment")


def test_downloading_an_unknown_attachment_id_is_a_404(client, tokens):
    response = client.get(
        f"{API}/attachments/00000000-0000-0000-0000-000000000000",
        headers=auth(tokens["admin"]),
    )
    assert_hidden(response, "unknown attachment id")


def test_a_soft_deleted_attachment_is_no_longer_downloadable(client, tokens, ticket):
    uploaded = _upload(client, tokens["requester"], ticket["id"], "gone.png")
    assert_status(uploaded, 201)
    attachment_id = uploaded.json()["id"]

    assert_status(
        client.delete(f"{API}/attachments/{attachment_id}", headers=auth(tokens["admin"])), 204
    )
    assert_hidden(
        client.get(f"{API}/attachments/{attachment_id}", headers=auth(tokens["requester"])),
        "soft-deleted attachment still downloadable",
    )


def test_a_requester_cannot_delete_an_attachment(client, tokens, ticket):
    uploaded = _upload(client, tokens["requester"], ticket["id"], "mine.png")
    response = client.delete(
        f"{API}/attachments/{uploaded.json()['id']}", headers=auth(tokens["requester"])
    )
    assert_status(response, 403, "requester deleted an attachment")


def test_uploading_to_someone_elses_ticket_is_hidden(client, db, tokens):
    victim = f.verified_requester(client, db)
    victim_ticket = f.make_ticket(client, victim["token"])
    attacker = f.verified_requester(client, db)
    response = _upload(client, attacker["token"], victim_ticket["id"], "planted.png")
    assert_hidden(response, "uploaded to another requester's ticket")


def test_replacing_an_attachment_from_another_ticket_is_rejected(client, tokens):
    first = f.make_ticket(client, tokens["requester"])
    second = f.make_ticket(client, tokens["requester"])
    original = _upload(client, tokens["requester"], first["id"], "v1.png")
    assert_status(original, 201)

    response = client.post(
        f"{API}/tickets/{second['id']}/attachments",
        files={"file": ("v2.png", PNG, "image/png")},
        params={"replaces_attachment_id": original.json()["id"]},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 422, "replaced an attachment belonging to another ticket")
