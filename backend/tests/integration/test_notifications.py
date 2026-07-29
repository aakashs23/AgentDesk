"""Pure-logic checks for the Phase 7 notification/webhook building blocks.

No DB — these guard the branch-y bits: variable interpolation, per-trigger
channel resolution, and HMAC signing / secret round-tripping.
"""

import hashlib
import hmac
from types import SimpleNamespace

from app.notifications import service as notifications
from app.notifications import templates
from app.webhooks import service as webhooks


def test_render_interpolates_known_vars():
    ticket = SimpleNamespace(display_id=42, subject="Login broken", status="open")
    user = SimpleNamespace(full_name="Dana Lee")
    out = templates.render(
        "{{ticket.display_id}} — {{ticket.subject}} ({{ticket.status}}) for {{user.full_name}}",
        ticket,
        user,
    )
    assert out == "AGT-42 — Login broken (open) for Dana Lee"


def test_render_leaves_unknown_vars_untouched():
    assert templates.render("{{ticket.nope}}", None, None) == "{{ticket.nope}}"


def test_channels_default_on_when_unset():
    user = SimpleNamespace(notification_preferences={})
    assert notifications.channels_for(user, "sla_warning") == ["email", "in_app"]


def test_channel_disabled_suppresses_only_that_channel():
    user = SimpleNamespace(notification_preferences={"sla_warning": {"email": False}})
    # email off for this trigger, in_app still on (Phase 7 checkpoint)
    assert notifications.channels_for(user, "sla_warning") == ["in_app"]
    # a different trigger is unaffected
    assert notifications.channels_for(user, "ticket_replied") == ["email", "in_app"]


def test_secret_round_trips():
    secret = webhooks.new_secret()
    assert webhooks.decrypt_secret(webhooks.encrypt_secret(secret)) == secret


def test_sign_matches_manual_hmac():
    body = b'{"event":"ticket_created"}'
    secret = "topsecret"
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert webhooks.sign(secret, body) == expected


if __name__ == "__main__":
    test_render_interpolates_known_vars()
    test_render_leaves_unknown_vars_untouched()
    test_channels_default_on_when_unset()
    test_channel_disabled_suppresses_only_that_channel()
    test_secret_round_trips()
    test_sign_matches_manual_hmac()
    print("ok")
