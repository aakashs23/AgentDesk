"""Notification trigger vocabulary + default template copy (Phase 7).

The Notification Service (App Flow §17) looks up the active template for a
firing `(trigger_type, channel)` and interpolates `{{ticket.*}}`/`{{user.*}}`
variables into it. When no active template exists it falls back to the
system-default text the calling event already provides (Doc 05 note on
`is_active`). These defaults are what `scripts/seed.py` writes into
`notification_templates` so an Admin has an editable starting point.
"""

import re

# Same vocabulary shared with automation_rules / webhooks (Doc 05 §10). Covers
# every App Flow §17 trigger the plan enumerates for Phase 7.
NOTIFICATION_TRIGGERS = (
    "ticket_assigned",
    "ticket_replied",
    "status_changed",
    "sla_warning",
    "sla_breached",
    "escalation",
    "mention",
    "ticket_closed",
    "automation_executed",
)

# slack/teams are future channels (App Flow §29) — no adapter yet, so not seeded.
CHANNELS = ("email", "in_app")

# subject/body per trigger; email uses the subject, in_app leaves it null (Doc 05).
_T = "{{ticket.display_id}} — {{ticket.subject}}"
_DEFAULT_COPY = {
    "ticket_assigned": (
        "Ticket {{ticket.display_id}} assigned to you",
        f"{_T} was assigned to you.",
    ),
    "ticket_replied": ("New reply on {{ticket.display_id}}", f"There is a new reply on {_T}."),
    "status_changed": (
        "Ticket {{ticket.display_id}} status changed",
        f"{_T} is now {{ticket.status}}.",
    ),
    "sla_warning": (
        "SLA warning on {{ticket.display_id}}",
        f"{_T} is approaching its SLA deadline.",
    ),
    "sla_breached": (
        "SLA breached on {{ticket.display_id}}",
        f"{_T} has breached its SLA deadline.",
    ),
    "escalation": ("Ticket {{ticket.display_id}} escalated to you", f"{_T} was escalated to you."),
    "mention": (
        "You were mentioned on {{ticket.display_id}}",
        f"{{user.full_name}}, you were mentioned on {_T}.",
    ),
    "ticket_closed": ("Ticket {{ticket.display_id}} closed", f"{_T} has been closed."),
    "automation_executed": (
        "Automation ran on {{ticket.display_id}}",
        f"An automation rule ran on {_T}.",
    ),
}


def default_templates() -> list[dict]:
    """One row spec per (trigger, channel); in_app has no subject line."""
    rows = []
    for trigger, (subject, body) in _DEFAULT_COPY.items():
        for channel in CHANNELS:
            rows.append(
                {
                    "trigger_type": trigger,
                    "channel": channel,
                    "subject_template": subject if channel == "email" else None,
                    "body_template": body,
                }
            )
    return rows


_VAR_RE = re.compile(r"{{\s*([\w.]+)\s*}}")


def render(template_str: str, ticket, user) -> str:
    """Interpolate the supported `{{ticket.*}}`/`{{user.*}}` variables."""
    values = {
        "ticket.display_id": f"AGT-{ticket.display_id}" if ticket else "",
        "ticket.subject": ticket.subject if ticket else "",
        "ticket.status": ticket.status if ticket else "",
        "user.full_name": user.full_name if user else "",
    }
    return _VAR_RE.sub(lambda m: str(values.get(m.group(1), m.group(0))), template_str)
