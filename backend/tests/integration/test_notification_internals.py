"""Notification plumbing: template rendering, channel preferences, and the
mailer's two delivery paths.

Pure units, no HTTP — these are the pieces every §17 trigger routes through, and
testing them directly is far cheaper than provoking each trigger end to end.
"""

from types import SimpleNamespace

import pytest

from app.notifications import mailer, templates
from app.notifications import service as notifications

TICKET = SimpleNamespace(display_id=42, subject="Printer on fire", status="open")
USER = SimpleNamespace(full_name="Ada Lovelace", notification_preferences={})


# --- Template rendering ---


@pytest.mark.parametrize(
    "template,expected",
    [
        ("{{ticket.display_id}}", "AGT-42"),
        ("{{ticket.subject}}", "Printer on fire"),
        ("{{ticket.status}}", "open"),
        ("{{user.full_name}}", "Ada Lovelace"),
        ("{{ ticket.subject }}", "Printer on fire"),  # tolerant of inner spaces
        ("Ticket {{ticket.display_id}} — {{ticket.subject}}", "Ticket AGT-42 — Printer on fire"),
        ("no variables here", "no variables here"),
        ("", ""),
    ],
)
def test_render_interpolates_the_supported_variables(template, expected):
    assert templates.render(template, TICKET, USER) == expected


@pytest.mark.parametrize(
    "template", ["{{ticket.password}}", "{{user.email}}", "{{unknown}}", "{{ticket}}"]
)
def test_render_leaves_unsupported_variables_untouched(template):
    """Unknown names are left verbatim rather than resolved or blanked — an
    admin's typo stays visible instead of silently rendering as nothing."""
    assert templates.render(template, TICKET, USER) == template


def test_render_tolerates_a_missing_ticket_or_user():
    """Not every trigger has a ticket (or a resolvable user) attached."""
    assert templates.render("[{{ticket.subject}}]", None, USER) == "[]"
    assert templates.render("[{{user.full_name}}]", TICKET, None) == "[]"


def test_default_templates_cover_every_trigger_and_channel():
    rows = templates.default_templates()
    pairs = {(r["trigger_type"], r["channel"]) for r in rows}
    expected = {
        (trigger, channel)
        for trigger in templates.NOTIFICATION_TRIGGERS
        for channel in templates.CHANNELS
    }
    assert pairs == expected
    assert len(rows) == len(expected), "default_templates produced duplicates"


def test_only_the_email_channel_carries_a_subject_line():
    """Doc 05: in-app notifications have no subject."""
    for row in templates.default_templates():
        if row["channel"] == "email":
            assert row["subject_template"], row
        else:
            assert row["subject_template"] is None, row
        assert row["body_template"], row


# --- Channel preferences ---


def test_an_absent_preference_means_the_channel_is_on():
    user = SimpleNamespace(notification_preferences={})
    assert notifications.channels_for(user, "sla_warning") == list(templates.CHANNELS)


def test_a_null_preferences_column_is_treated_as_empty():
    user = SimpleNamespace(notification_preferences=None)
    assert notifications.channels_for(user, "sla_warning") == list(templates.CHANNELS)


def test_disabling_one_channel_leaves_the_others_on():
    user = SimpleNamespace(notification_preferences={"sla_warning": {"email": False}})
    assert notifications.channels_for(user, "sla_warning") == ["in_app"]


def test_disabling_every_channel_silences_the_trigger():
    user = SimpleNamespace(
        notification_preferences={"sla_warning": {"email": False, "in_app": False}}
    )
    assert notifications.channels_for(user, "sla_warning") == []


def test_preferences_are_scoped_to_one_trigger():
    user = SimpleNamespace(
        notification_preferences={"sla_warning": {"email": False, "in_app": False}}
    )
    assert notifications.channels_for(user, "ticket_assigned") == list(templates.CHANNELS)


# --- Mailer ---


def test_without_smtp_configured_the_email_is_logged_not_sent(monkeypatch, caplog):
    """The dev sandbox path: no SMTP connection is attempted."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "smtp_host", "")

    def explode(*_args, **_kwargs):
        raise AssertionError("SMTP was contacted with no host configured")

    monkeypatch.setattr(mailer.smtplib, "SMTP", explode)
    with caplog.at_level("INFO", logger="agentdesk.mailer"):
        mailer.send_email("someone@example.com", "Subject line", "Body text")
    assert "someone@example.com" in caplog.text


def test_with_smtp_configured_the_message_is_sent(monkeypatch):
    """Covers the real delivery path: STARTTLS, login, and a well-formed message."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 2525)
    monkeypatch.setattr(settings, "smtp_user", "mailer@example.com")
    monkeypatch.setattr(settings, "smtp_password", "hunter2")

    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            events.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            events.append(("starttls",))

        def login(self, user, password):
            events.append(("login", user, password))

        def send_message(self, message):
            events.append(("send", message))

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    mailer.send_email("to@example.com", "Hello", "Body text")

    assert events[0] == ("connect", "smtp.example.com", 2525)
    assert ("starttls",) in events
    assert ("login", "mailer@example.com", "hunter2") in events

    message = next(e[1] for e in events if e[0] == "send")
    assert message["To"] == "to@example.com"
    assert message["From"] == "mailer@example.com"
    assert message["Subject"] == "Hello"
    assert message.get_content().strip() == "Body text"


def test_an_anonymous_smtp_relay_skips_the_login_step(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "relay.example.com")
    monkeypatch.setattr(settings, "smtp_user", "")

    events = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            events.append("starttls")

        def login(self, *_args):
            events.append("login")

        def send_message(self, _message):
            events.append("send")

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    mailer.send_email("to@example.com", "Hello", "Body")
    assert "login" not in events, "an anonymous relay was sent credentials"
    assert "send" in events


def test_a_dead_relay_does_not_raise_at_the_caller(monkeypatch):
    """The invite/reset/ack callers have already committed their row when the mail
    goes out — a refused relay must not turn that into a 500."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "smtp_host", "relay.example.com")

    def explode(*_args, **_kwargs):
        raise mailer.smtplib.SMTPConnectError(421, "service not available")

    monkeypatch.setattr(mailer.smtplib, "SMTP", explode)
    mailer.send_email("to@example.com", "Hello", "Body")  # no exception
