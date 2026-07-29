"""Unicode handling end to end.

Text goes in as JSON, through Postgres, back out as JSON, and through full-text
and trigram search on the way. Every script must survive that round trip byte
for byte — no mangling, no normalisation, no truncation mid-codepoint.
"""

import pytest

from tests.helpers import factories as f
from tests.helpers.assertions import assert_status
from tests.helpers.auth import API, auth

SAMPLES = {
    "emoji": "🔥 Printer on fire 🚒",
    "emoji_zwj": "👨‍👩‍👧‍👦 family account",
    "chinese": "登录问题：无法访问账户",
    "japanese": "ログインできません",
    "korean": "로그인 문제",
    "arabic": "لا أستطيع تسجيل الدخول",
    "hebrew": "אני לא יכול להתחבר",
    "tamil": "என்னால் உள்நுழைய முடியவில்லை",
    "hindi": "मैं लॉग इन नहीं कर सकता",
    "thai": "ฉันเข้าสู่ระบบไม่ได้",
    "cyrillic": "Не могу войти в систему",
    "greek": "Δεν μπορώ να συνδεθώ",
    "combining": "é vs é",  # precomposed vs decomposed
    "rtl_override": "invoice‮gnp.exe",
    "rtl_mark": "a‏b",
    "zero_width": "in​visible",
    "math_script": "𝕌𝕟𝕚𝕔𝕠𝕕𝕖 𝔦𝔰𝔰𝔲𝔢",
    "surrogate_pair": "𝓯𝓪𝓷𝓬𝔂",
    "nbsp": "non breaking",
    "accents": "Àéîõü Ñ ç",
}


@pytest.mark.parametrize("label,text", SAMPLES.items(), ids=list(SAMPLES))
def test_unicode_survives_the_ticket_round_trip(client, tokens, label, text):
    created = client.post(
        f"{API}/tickets",
        json={"subject": text, "description": f"{text}\n{text}", "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_status(created, 201, label)
    assert created.json()["subject"] == text, "subject was altered in transit"

    fetched = client.get(f"{API}/tickets/{created.json()['id']}", headers=auth(tokens["requester"]))
    assert_status(fetched, 200, label)
    assert fetched.json()["subject"] == text, "subject was altered in storage"
    assert fetched.json()["description"] == f"{text}\n{text}"


@pytest.mark.parametrize("label,text", SAMPLES.items(), ids=list(SAMPLES))
def test_unicode_survives_the_comment_round_trip(client, tokens, label, text):
    ticket = f.make_ticket(client, tokens["requester"])
    created = f.comment(client, tokens["requester"], ticket["id"], text)
    assert_status(created, 201, label)
    assert created.json()["body"] == text

    listed = client.get(f"{API}/tickets/{ticket['id']}/comments", headers=auth(tokens["requester"]))
    assert text in [c["body"] for c in listed.json()]


@pytest.mark.parametrize("label,text", SAMPLES.items(), ids=list(SAMPLES))
def test_searching_for_unicode_never_errors(client, tokens, label, text):
    response = client.get(
        f"{API}/search/tickets", params={"q": text}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200, f"search {label}")
    assert response.json()["query"] == text


def test_a_unicode_ticket_is_findable_by_its_own_text(client, tokens):
    """Search must not be ASCII-only: a CJK subject has to match a CJK query."""
    marker = f"独角兽{f.rand()}"
    created = client.post(
        f"{API}/tickets",
        json={"subject": f"{marker} 登录问题", "description": "详情", "channel": "portal"},
        headers=auth(tokens["admin"]),
    )
    assert_status(created, 201)

    response = client.get(
        f"{API}/search/tickets", params={"q": marker}, headers=auth(tokens["admin"])
    )
    assert_status(response, 200)
    assert created.json()["id"] in {t["id"] for t in response.json()["tickets"]}, (
        "a non-Latin subject could not be found by its own distinctive token"
    )


@pytest.mark.parametrize("name", ["日本語タグ", "étiquette", "тег", "🏷️", "tag-ünïcödé"])
def test_unicode_tag_names_are_accepted(client, tokens, name):
    unique = f"{name}-{f.rand()}"
    response = client.post(f"{API}/tags", json={"name": unique}, headers=auth(tokens["agent"]))
    assert_status(response, 201, f"tag={unique!r}")
    assert response.json()["name"] == unique


def test_unicode_full_names_survive_registration(client, db):
    name = "Aakash Sivakumar — 阿卡什 🎯"
    created = f.register_requester(client, full_name=name)
    assert created["user"]["full_name"] == name


def test_unicode_in_an_attachment_filename_is_preserved(client, tokens):
    ticket = f.make_ticket(client, tokens["requester"])
    filename = "スクリーンショット.png"
    uploaded = client.post(
        f"{API}/tickets/{ticket['id']}/attachments",
        files={"file": (filename, b"\x89PNG" + b"\x00" * 32, "image/png")},
        headers=auth(tokens["requester"]),
    )
    assert_status(uploaded, 201)
    downloaded = client.get(
        f"{API}/attachments/{uploaded.json()['id']}", headers=auth(tokens["requester"])
    )
    assert_status(downloaded, 200)
    # RFC 5987 encoding, never a raw non-ASCII byte in the header
    disposition = downloaded.headers["content-disposition"]
    assert disposition.isascii(), f"non-ASCII bytes in a header: {disposition!r}"


def test_unicode_in_an_automation_condition_matches(client, db, tokens):
    marker = f"緊急{f.rand()}"
    rule = f.make_rule(
        client,
        tokens["admin"],
        conditions=[{"field": "subject", "op": "contains", "value": marker}],
        actions=[{"type": "set_priority", "priority_id": f.catalog(db)["priorities"]["High"]}],
    )
    created = client.post(
        f"{API}/tickets",
        json={"subject": f"{marker} サーバーダウン", "description": "d", "channel": "portal"},
        headers=auth(tokens["requester"]),
    )
    assert_status(created, 201)
    assert created.json()["priority_id"] == f.catalog(db)["priorities"]["High"], (
        "a unicode automation condition did not match"
    )
    f.delete_rule(client, tokens["admin"], rule["id"])
