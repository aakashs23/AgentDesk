"""Admin configuration endpoints — Phase 6 ships the automation-rules slice
(TRD §3 Admin Configuration; App Flow §25 builder flow). Admin-only.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from app.audit import service as audit
from app.auth.deps import SessionDep, require_role
from app.models import AutomationExecutionLog, AutomationRule, Ticket, User
from app.tickets.schemas import TicketOut
from app.workflow.automation import CONDITION_FIELDS, TRIGGERS, matches

router = APIRouter(prefix="/admin", tags=["admin"])

AdminUser = Annotated[User, Depends(require_role("admin"))]


class RuleIn(BaseModel):
    name: str
    trigger_type: str
    conditions: list[dict] = []
    actions: list[dict] = []
    priority: int = 100
    is_active: bool = True


class RulePatch(BaseModel):
    name: str | None = None
    trigger_type: str | None = None
    conditions: list[dict] | None = None
    actions: list[dict] | None = None
    priority: int | None = None
    is_active: bool | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    trigger_type: str
    conditions: list
    actions: list
    priority: int
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ExecutionLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    automation_rule_id: uuid.UUID
    ticket_id: uuid.UUID | None
    execution_status: str
    execution_started_at: datetime
    execution_completed_at: datetime | None
    error_message: str | None
    created_at: datetime


class PreviewIn(BaseModel):
    conditions: list[dict] = []


def _validate_rule(trigger_type: str | None, conditions: list | None) -> None:
    if trigger_type is not None and trigger_type not in TRIGGERS:
        raise HTTPException(status_code=422, detail=f"Unknown trigger_type: {trigger_type}")
    for cond in conditions or []:
        if cond.get("field") not in CONDITION_FIELDS:
            raise HTTPException(
                status_code=422, detail=f"Unknown condition field: {cond.get('field')}"
            )


async def _get_rule(session, rule_id: uuid.UUID) -> AutomationRule:
    rule = await session.get(AutomationRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return rule


@router.get("/automation-rules")
async def list_rules(caller: AdminUser, session: SessionDep) -> list[RuleOut]:
    result = await session.execute(
        sa.select(AutomationRule).order_by(AutomationRule.priority, AutomationRule.created_at)
    )
    return [RuleOut.model_validate(r) for r in result.scalars()]


@router.post("/automation-rules", status_code=201)
async def create_rule(body: RuleIn, caller: AdminUser, session: SessionDep) -> RuleOut:
    _validate_rule(body.trigger_type, body.conditions)
    rule = AutomationRule(**body.model_dump(), created_by=caller.id)
    session.add(rule)
    await session.flush()
    audit.log(
        session,
        "automation_rule",
        rule.id,
        caller.id,
        "created",
        after={"name": rule.name, "trigger_type": rule.trigger_type, "is_active": rule.is_active},
    )
    await session.commit()
    return RuleOut.model_validate(rule)


@router.patch("/automation-rules/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID, body: RulePatch, caller: AdminUser, session: SessionDep
) -> RuleOut:
    rule = await _get_rule(session, rule_id)
    changes = body.model_dump(exclude_unset=True)
    _validate_rule(changes.get("trigger_type"), changes.get("conditions"))
    before = {k: getattr(rule, k) for k in changes if not isinstance(getattr(rule, k), list)}
    for key, value in changes.items():
        setattr(rule, key, value)
    rule.updated_at = datetime.now(UTC)
    audit.log(
        session,
        "automation_rule",
        rule.id,
        caller.id,
        "updated",
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return RuleOut.model_validate(rule)


@router.delete("/automation-rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: uuid.UUID, caller: AdminUser, session: SessionDep) -> Response:
    rule = await _get_rule(session, rule_id)
    in_use = await session.execute(
        sa.select(AutomationExecutionLog.id)
        .where(AutomationExecutionLog.automation_rule_id == rule_id)
        .limit(1)
    )
    if in_use.first():
        # execution history references the rule — deactivate instead of orphaning logs
        raise HTTPException(
            status_code=409,
            detail="Rule has execution history; deactivate it instead (PATCH is_active=false)",
        )
    audit.log(session, "automation_rule", rule.id, caller.id, "deleted", before={"name": rule.name})
    await session.delete(rule)
    await session.commit()
    return Response(status_code=204)


@router.post("/automation-rules/preview")
async def preview_rule(body: PreviewIn, caller: AdminUser, session: SessionDep) -> list[TicketOut]:
    """App Flow §25 step 5: sample of existing tickets the draft rule would match."""
    _validate_rule(None, body.conditions)
    query = sa.select(Ticket).order_by(Ticket.created_at.desc()).limit(200)
    tickets = list((await session.execute(query)).scalars())
    sample = []
    for ticket in tickets:
        try:
            if matches(ticket, body.conditions):
                sample.append(ticket)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        if len(sample) >= 10:
            break
    return [TicketOut.model_validate(t) for t in sample]


@router.get("/automation-logs")
async def list_execution_logs(
    caller: AdminUser,
    session: SessionDep,
    ticket_id: uuid.UUID | None = None,
    rule_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ExecutionLogOut]:
    query = sa.select(AutomationExecutionLog).order_by(AutomationExecutionLog.created_at.desc())
    if ticket_id:
        query = query.where(AutomationExecutionLog.ticket_id == ticket_id)
    if rule_id:
        query = query.where(AutomationExecutionLog.automation_rule_id == rule_id)
    result = await session.execute(query.limit(limit))
    return [ExecutionLogOut.model_validate(r) for r in result.scalars()]
