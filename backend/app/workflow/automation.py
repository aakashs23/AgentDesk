"""Automation Engine runtime (TRD §14; App Flow Doc 03 §15).

`dispatch(session, trigger_type, ticket)` runs at write time inside the
caller's transaction: fetch active rules for the trigger ordered by priority,
evaluate each rule's conditions, execute matched actions, and write one
`automation_execution_logs` row per evaluation — matched, skipped, or failed.

Conflicts (§15 step 6): two matched rules writing the same ticket field —
the higher-priority (lower number) rule wins; the losing action is suppressed
and the conflict is written to the Audit Log.
"""

import logging
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.models import (
    AutomationExecutionLog,
    AutomationRule,
    Priority,
    Queue,
    Role,
    Tag,
    Ticket,
    TicketTag,
    User,
)
from app.notifications import service as notifications
from app.workflow import engine

logger = logging.getLogger("agentdesk")

TRIGGERS = {
    "ticket_created",
    "status_changed",
    "comment_added",
    "tag_added",
    "sla_warning",
    "sla_breached",
}
CONDITION_FIELDS = {
    "category_id",
    "priority_id",
    "queue_id",
    "assignee_id",
    "requester_id",
    "status",
    "channel",
    "subject",
    "description",
}
# the vocabulary `_execute_actions` dispatches on — validated at rule creation
ACTION_TYPES = {"assign", "set_priority", "add_tag", "notify", "escalate"}
# ticket fields a rule action can write — the conflict-resolution slots (§15)
_SLOTS = ("assignee_id", "queue_id", "priority_id")


def _now() -> datetime:
    return datetime.now(UTC)


def matches(ticket: Ticket, conditions: list[dict]) -> bool:
    """AND across conditions. Unknown field/op raises — surfaces as a failed run."""
    for cond in conditions:
        field, op, value = cond.get("field"), cond.get("op", "eq"), cond.get("value")
        if field not in CONDITION_FIELDS:
            raise ValueError(f"Unknown condition field: {field}")
        actual = getattr(ticket, field, None)
        actual_str = str(actual) if actual is not None else None
        if op == "eq":
            ok = actual_str == (str(value) if value is not None else None)
        elif op == "ne":
            ok = actual_str != (str(value) if value is not None else None)
        elif op == "in":
            ok = actual_str in [str(v) for v in value]
        elif op == "contains":
            ok = isinstance(actual, str) and str(value).lower() in actual.lower()
        else:
            raise ValueError(f"Unknown condition op: {op}")
        if not ok:
            return False
    return True


async def _find_team_lead(session: AsyncSession, ticket: Ticket) -> User | None:
    team_id = None
    if ticket.queue_id:
        queue = await session.get(Queue, ticket.queue_id)
        team_id = queue.team_id if queue else None
    if team_id is None and ticket.assignee_id:
        assignee = await session.get(User, ticket.assignee_id)
        team_id = assignee.team_id if assignee else None
    if team_id is None:
        return None
    result = await session.execute(
        sa.select(User)
        .join(Role, Role.id == User.role_id)
        .where(Role.name == "team_lead", User.team_id == team_id, User.is_active.is_(True))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _claim(
    session: AsyncSession,
    ticket: Ticket,
    slots: dict[str, uuid.UUID],
    field: str,
    rule: AutomationRule,
) -> bool:
    """True if this rule may write `field`; logs the §15 conflict when it may not."""
    winner = slots.get(field)
    if winner is None:
        slots[field] = rule.id
        return True
    audit.log(
        session,
        "ticket",
        ticket.id,
        None,
        "automation_conflict",
        after={
            "field": field,
            "winning_rule_id": str(winner),
            "suppressed_rule_id": str(rule.id),
        },
    )
    return False


async def _execute_actions(
    session: AsyncSession, ticket: Ticket, rule: AutomationRule, slots: dict
) -> None:
    for action in rule.actions:
        kind = action.get("type")
        # Targets are validated *before* the slot is claimed: a rule that then
        # raises would otherwise keep the slot, suppressing the next rule that
        # wants the field as a §15 conflict — so a valid rule silently never runs.
        if kind == "assign":
            if action.get("queue_id"):
                queue_id = uuid.UUID(action["queue_id"])
                if await session.get(Queue, queue_id) is None:
                    raise ValueError(f"assign: unknown queue {action['queue_id']}")
                if await _claim(session, ticket, slots, "queue_id", rule):
                    ticket.queue_id = queue_id
            if action.get("assignee_id"):
                assignee_id = uuid.UUID(action["assignee_id"])
                if await session.get(User, assignee_id) is None:
                    raise ValueError(f"assign: unknown user {action['assignee_id']}")
                if await _claim(session, ticket, slots, "assignee_id", rule):
                    ticket.assignee_id = assignee_id
        elif kind == "set_priority":
            priority_id = uuid.UUID(action["priority_id"])
            if await session.get(Priority, priority_id) is None:
                raise ValueError(f"set_priority: unknown priority {action['priority_id']}")
            if await _claim(session, ticket, slots, "priority_id", rule):
                ticket.priority_id = priority_id
        elif kind == "add_tag":
            tag_id = uuid.UUID(action["tag_id"])
            if await session.get(Tag, tag_id) is None:
                raise ValueError(f"add_tag: unknown tag {tag_id}")
            if await session.get(TicketTag, (ticket.id, tag_id)) is None:
                session.add(TicketTag(ticket_id=ticket.id, tag_id=tag_id, added_by=None))
        elif kind == "notify":
            user_id = action.get("user_id") or ticket.assignee_id
            if user_id:
                message = action.get("message")
                await notifications.notify(
                    session,
                    uuid.UUID(str(user_id)),
                    ticket.id,
                    "automation_executed",
                    f"[AGT-{ticket.display_id}] {rule.name}",
                    message or f"Automation rule '{rule.name}' matched this ticket.",
                    override_template=message is not None,
                )
        elif kind == "escalate":
            lead = await _find_team_lead(session, ticket)
            if lead and await _claim(session, ticket, slots, "assignee_id", rule):
                ticket.assignee_id = lead.id
                await notifications.notify(
                    session,
                    lead.id,
                    ticket.id,
                    "escalation",
                    f"[AGT-{ticket.display_id}] Escalated to you",
                    f"Automation rule '{rule.name}' escalated ticket AGT-{ticket.display_id}.",
                )
        else:
            raise ValueError(f"Unknown action type: {kind}")
    ticket.updated_at = _now()


async def dispatch(session: AsyncSession, trigger_type: str, ticket: Ticket) -> None:
    """Evaluate all active rules for this trigger against the ticket.

    Runs inside the caller's transaction; a failing rule is logged as failed
    and never breaks the triggering request. Actions do not re-fire triggers,
    so rules cannot cascade (§15 keeps execution single-level).
    """
    result = await session.execute(
        sa.select(AutomationRule)
        .where(AutomationRule.trigger_type == trigger_type, AutomationRule.is_active.is_(True))
        .order_by(AutomationRule.priority, AutomationRule.created_at)
    )
    rules = list(result.scalars())
    if not rules:
        return
    slots: dict[str, uuid.UUID] = {}
    for rule in rules:
        log = AutomationExecutionLog(
            automation_rule_id=rule.id, ticket_id=ticket.id, execution_status="skipped"
        )
        try:
            if matches(ticket, rule.conditions):
                await _execute_actions(session, ticket, rule, slots)
                audit.log(
                    session,
                    "ticket",
                    ticket.id,
                    None,
                    "automation_executed",
                    after={"rule_id": str(rule.id), "rule_name": rule.name},
                )
                log.execution_status = "success"
        except Exception as exc:  # a broken rule must never break the request
            log.execution_status = "failed"
            log.error_message = str(exc)
            logger.warning("automation rule %s failed on ticket %s: %s", rule.id, ticket.id, exc)
        log.execution_completed_at = _now()
        session.add(log)

    # Rule-driven assignment counts as pickup: New → Open (system), same as §10
    if ticket.status == "new" and ("assignee_id" in slots or "queue_id" in slots):
        await engine.transition(session, ticket, "open", None, None)
