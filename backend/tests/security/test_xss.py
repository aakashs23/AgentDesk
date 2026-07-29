"""Cross-site scripting: storage, retrieval, and the response headers.

This is a JSON API, so the correct behaviour is *not* to mangle the payload on
the way in — HTML escaping belongs to whatever renders it. What the API must
guarantee is that a script payload can never be served back in a context where
a browser would execute it: the content type stays `application/json`, and
downloads are forced as attachments rather than rendered inline.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth

PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    "javascript:alert(1)",
    '"><script>alert(document.cookie)</script>',
    "<iframe src='javascript:alert(1)'></iframe>",
    "<body onload=alert(1)>",
    "'-alert(1)-'",
    '<a href="javascript:alert(1)">click</a>',
    "&lt;script&gt;alert(1)&lt;/script&gt;",
]


@pytest.mark.parametrize("payload", PAYLOADS)
def test_script_payloads_round_trip_verbatim_as_json(client, tokens, payload):
    created = client.post(
        f"{API}/tickets",
        json={"subject": payload, "description": payload, "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_status(created, 201, f"payload={payload!r}")
    body = created.json()
    assert body["subject"] == payload, "payload was silently rewritten"
    assert created.headers["content-type"].startswith("application/json")

    fetched = client.get(f"{API}/tickets/{body['id']}", headers=auth(tokens["requester"]))
    assert_status(fetched, 200)
    assert fetched.json()["subject"] == payload
    assert fetched.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("payload", PAYLOADS[:5])
def test_comment_bodies_are_never_served_as_html(client, tokens, payload):
    ticket = f.make_ticket(client, tokens["requester"])
    created = f.comment(client, tokens["requester"], ticket["id"], payload)
    assert_status(created, 201)

    listed = client.get(f"{API}/tickets/{ticket['id']}/comments", headers=auth(tokens["requester"]))
    assert listed.headers["content-type"].startswith("application/json")
    assert payload in [c["body"] for c in listed.json()]


def test_error_responses_do_not_reflect_the_payload_as_html(client, tokens):
    """A reflected 422 body must still be JSON, never text/html."""
    response = client.post(
        f"{API}/tickets",
        json={"subject": "", "description": "<script>alert(1)</script>", "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_status(response, 422)
    assert response.headers["content-type"].startswith("application/json")


def test_search_echoes_the_query_as_json_only(client, tokens):
    payload = "<script>alert('xss')</script>"
    response = client.get(
        f"{API}/search/tickets", params={"q": payload}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["query"] == payload


def test_an_svg_upload_is_served_as_an_attachment_not_inline(client, tokens):
    """SVG is script-capable. It is an accepted image type, so the download must
    force a save rather than render in the browsing context."""
    ticket = f.make_ticket(client, tokens["requester"])
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>'
    uploaded = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": ("payload.svg", svg, "image/svg+xml")},
        headers=auth(tokens["requester"]),
    )
    assert_status(uploaded, 201, "svg upload")

    downloaded = client.get(
        f"{API}/attachments/{uploaded.json()['id']}", headers=auth(tokens["requester"])
    )
    assert_status(downloaded, 200)
    disposition = downloaded.headers.get("content-disposition", "")
    assert disposition.startswith("attachment"), (
        f"SVG served with Content-Disposition {disposition!r} — a browser would execute it"
    )


def test_a_quote_in_a_filename_cannot_break_out_of_the_content_disposition_header(client, tokens):
    """Header injection via filename: quotes/CRLF must be encoded, not literal."""
    ticket = f.make_ticket(client, tokens["requester"])
    uploaded = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": ('evil";x=y.png', b"\x89PNG\r\n" + b"\x00" * 32, "image/png")},
        headers=auth(tokens["requester"]),
    )
    assert_status(uploaded, 201)

    downloaded = client.get(
        f"{API}/attachments/{uploaded.json()['id']}", headers=auth(tokens["requester"])
    )
    assert_status(downloaded, 200)
    disposition = downloaded.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition
    # Exactly one header, and no smuggled second one
    assert "x=y" not in downloaded.headers or disposition.count("filename") == 1
