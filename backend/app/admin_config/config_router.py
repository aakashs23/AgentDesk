"""Admin configuration CRUD — Phase 12 (TRD §3 "Categories / Priorities / SLA
Rules / Automation Rules / Queues / Tags"; RBAC per Doc 05 §6: Admin only).

Reads for categories and priorities already exist for every role at
`/categories` / `/priorities` (taxonomy_router) — every surface needs them for a
dropdown — so this module adds only the write half for those two, and the whole
set for teams, queues and SLA policies, which nobody but an Admin may see.

Two contracts run through the whole file:

- **Deletes never orphan.** A config row still referenced by a ticket, another
  config row, or AI history returns 409 and the Admin is told to edit instead.
  Same shape as the automation-rule delete guard built in Phase 6.
- **Every change is audited.** Doc 06's Phase 12 checkpoint requires that
  configuration edits show up in the Audit Log, so each handler calls
  `audit.log` before committing.

`/admin/config` (TRD) is deliberately absent: statuses are a fixed vocabulary
owned by the workflow engine, not a table, and branding has no column in Doc 05
to store it — adding one would break the schema invariant.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

from app.admin_config.taxonomy_router import CategoryOut, PriorityOut
from app.audit import service as audit
from app.auth.deps import SessionDep, require_role
from app.models import (
    AiClassificationHistory,
    AuditLog,
    Category,
    KnowledgeBaseArticle,
    Priority,
    Queue,
    SlaPolicy,
    Team,
    Ticket,
    User,
)
from app.validators import SafeText

router = APIRouter(prefix="/admin", tags=["admin config"])

AdminUser = Annotated[User, Depends(require_role("admin"))]

Name = Annotated[SafeText, Field(min_length=1, max_length=100)]
# Doc 04 stores priority colours as hex; the picker sends exactly this form.
HexColor = Annotated[str, Field(pattern="^#[0-9a-fA-F]{6}$")]


# --- Shared helpers ---------------------------------------------------------


async def _get(session: AsyncSession, model: type[SQLModel], row_id: uuid.UUID, what: str):
    row = await session.get(model, row_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{what} not found")
    return row


async def _reject_duplicate_name(
    session: AsyncSession, model, name: str, what: str, exclude: uuid.UUID | None = None
) -> None:
    """Names are what an Admin identifies these rows by, and the routing agent
    matches queues to categories *by name* — two rows sharing one is a silent
    misroute, not a cosmetic problem."""
    query = sa.select(model.id).where(sa.func.lower(model.name) == name.lower())
    if exclude:
        query = query.where(model.id != exclude)
    if (await session.execute(query.limit(1))).first():
        raise HTTPException(status_code=409, detail=f"A {what} named {name!r} already exists")


async def _reject_if_referenced(session: AsyncSession, what: str, *refs) -> None:
    """`refs` are (column, value) pairs: any hit means deleting would orphan."""
    for column, value in refs:
        if (await session.execute(sa.select(column).where(column == value).limit(1))).first():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This {what} is still in use by {column.table.name}; "
                    "reassign those records first"
                ),
            )


def _audited(session, entity: str, row, actor_id: uuid.UUID, action: str, **states) -> None:
    audit.log(session, entity, row.id, actor_id, action, **states)


def _state(row, *fields) -> dict:
    # audit_logs is JSONB — uuids and datetimes have to go in as strings.
    return {f: None if getattr(row, f) is None else str(getattr(row, f)) for f in fields}


# --- Teams ------------------------------------------------------------------


class TeamIn(BaseModel):
    name: Name


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


@router.get("/teams")
async def list_teams(caller: AdminUser, session: SessionDep) -> list[TeamOut]:
    query = sa.select(Team).order_by(Team.name)
    return [TeamOut.model_validate(t) for t in (await session.execute(query)).scalars()]


@router.post("/teams", status_code=201)
async def create_team(body: TeamIn, caller: AdminUser, session: SessionDep) -> TeamOut:
    await _reject_duplicate_name(session, Team, body.name, "team")
    team = Team(name=body.name)
    session.add(team)
    await session.flush()
    _audited(session, "team", team, caller.id, "created", after={"name": team.name})
    await session.commit()
    return TeamOut.model_validate(team)


@router.patch("/teams/{team_id}")
async def update_team(
    team_id: uuid.UUID, body: TeamIn, caller: AdminUser, session: SessionDep
) -> TeamOut:
    team = await _get(session, Team, team_id, "Team")
    await _reject_duplicate_name(session, Team, body.name, "team", exclude=team_id)
    before = _state(team, "name")
    team.name = body.name
    _audited(session, "team", team, caller.id, "updated", before=before, after={"name": team.name})
    await session.commit()
    return TeamOut.model_validate(team)


@router.delete("/teams/{team_id}", status_code=204)
async def delete_team(team_id: uuid.UUID, caller: AdminUser, session: SessionDep) -> Response:
    team = await _get(session, Team, team_id, "Team")
    await _reject_if_referenced(session, "team", (User.team_id, team_id), (Queue.team_id, team_id))
    _audited(session, "team", team, caller.id, "deleted", before={"name": team.name})
    await session.delete(team)
    await session.commit()
    return Response(status_code=204)


# --- Queues -----------------------------------------------------------------


class QueueIn(BaseModel):
    name: Name
    team_id: uuid.UUID | None = None


class QueuePatch(BaseModel):
    name: Name | None = None
    team_id: uuid.UUID | None = None


class QueueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    team_id: uuid.UUID | None
    created_at: datetime


@router.get("/queues")
async def list_queues(caller: AdminUser, session: SessionDep) -> list[QueueOut]:
    query = sa.select(Queue).order_by(Queue.name)
    return [QueueOut.model_validate(q) for q in (await session.execute(query)).scalars()]


@router.post("/queues", status_code=201)
async def create_queue(body: QueueIn, caller: AdminUser, session: SessionDep) -> QueueOut:
    await _reject_duplicate_name(session, Queue, body.name, "queue")
    if body.team_id:
        await _get(session, Team, body.team_id, "Team")
    queue = Queue(name=body.name, team_id=body.team_id)
    session.add(queue)
    await session.flush()
    _audited(session, "queue", queue, caller.id, "created", after=_state(queue, "name", "team_id"))
    await session.commit()
    return QueueOut.model_validate(queue)


@router.patch("/queues/{queue_id}")
async def update_queue(
    queue_id: uuid.UUID, body: QueuePatch, caller: AdminUser, session: SessionDep
) -> QueueOut:
    queue = await _get(session, Queue, queue_id, "Queue")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        await _reject_duplicate_name(session, Queue, changes["name"], "queue", exclude=queue_id)
    if changes.get("team_id"):
        await _get(session, Team, changes["team_id"], "Team")
    before = _state(queue, "name", "team_id")
    for key, value in changes.items():
        setattr(queue, key, value)
    # A queue moving between teams changes who can see every ticket in it
    # (`scope_tickets_to_caller` reads queue.team_id), so this is audited as a
    # permissions event, not a rename.
    _audited(
        session,
        "queue",
        queue,
        caller.id,
        "updated",
        before=before,
        after=_state(queue, "name", "team_id"),
    )
    await session.commit()
    return QueueOut.model_validate(queue)


@router.delete("/queues/{queue_id}", status_code=204)
async def delete_queue(queue_id: uuid.UUID, caller: AdminUser, session: SessionDep) -> Response:
    queue = await _get(session, Queue, queue_id, "Queue")
    await _reject_if_referenced(session, "queue", (Ticket.queue_id, queue_id))
    _audited(session, "queue", queue, caller.id, "deleted", before={"name": queue.name})
    await session.delete(queue)
    await session.commit()
    return Response(status_code=204)


# --- Categories (write half; reads live at GET /categories) -----------------


class CategoryIn(BaseModel):
    name: Name
    parent_id: uuid.UUID | None = None


class CategoryPatch(BaseModel):
    name: Name | None = None
    parent_id: uuid.UUID | None = None


async def _resolve_parent(
    session: AsyncSession, parent_id: uuid.UUID | None, child_id: uuid.UUID | None = None
) -> None:
    """Validate a proposed parent: it must exist, and must not sit below the
    child. Without the walk, `A.parent = B; B.parent = A` is accepted and then
    hangs `_top_level_category_name`, which loops until it finds a root."""
    seen = {child_id} if child_id else set()
    node_id = parent_id
    while node_id is not None:
        if node_id in seen:
            raise HTTPException(status_code=422, detail="A category cannot be its own ancestor")
        seen.add(node_id)
        parent = await _get(session, Category, node_id, "Parent category")
        node_id = parent.parent_id


@router.post("/categories", status_code=201)
async def create_category(body: CategoryIn, caller: AdminUser, session: SessionDep) -> CategoryOut:
    await _reject_duplicate_name(session, Category, body.name, "category")
    await _resolve_parent(session, body.parent_id)
    category = Category(name=body.name, parent_id=body.parent_id)
    session.add(category)
    await session.flush()
    _audited(
        session,
        "category",
        category,
        caller.id,
        "created",
        after=_state(category, "name", "parent_id"),
    )
    await session.commit()
    return CategoryOut.model_validate(category)


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: uuid.UUID, body: CategoryPatch, caller: AdminUser, session: SessionDep
) -> CategoryOut:
    category = await _get(session, Category, category_id, "Category")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        await _reject_duplicate_name(
            session, Category, changes["name"], "category", exclude=category_id
        )
    if "parent_id" in changes:
        await _resolve_parent(session, changes["parent_id"], category_id)
    before = _state(category, "name", "parent_id")
    for key, value in changes.items():
        setattr(category, key, value)
    _audited(
        session,
        "category",
        category,
        caller.id,
        "updated",
        before=before,
        after=_state(category, "name", "parent_id"),
    )
    await session.commit()
    return CategoryOut.model_validate(category)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(
    category_id: uuid.UUID, caller: AdminUser, session: SessionDep
) -> Response:
    category = await _get(session, Category, category_id, "Category")
    await _reject_if_referenced(
        session,
        "category",
        (Ticket.category_id, category_id),
        (Category.parent_id, category_id),
        (SlaPolicy.category_id, category_id),
        (KnowledgeBaseArticle.category_id, category_id),
        (AiClassificationHistory.predicted_category_id, category_id),
        (AiClassificationHistory.corrected_category_id, category_id),
    )
    _audited(session, "category", category, caller.id, "deleted", before={"name": category.name})
    await session.delete(category)
    await session.commit()
    return Response(status_code=204)


# --- Priorities (write half; reads live at GET /priorities) -----------------


class PriorityIn(BaseModel):
    name: Name
    rank: Annotated[int, Field(ge=1, le=100)]
    color_hex: HexColor


class PriorityPatch(BaseModel):
    name: Name | None = None
    rank: Annotated[int, Field(ge=1, le=100)] | None = None
    color_hex: HexColor | None = None


@router.post("/priorities", status_code=201)
async def create_priority(body: PriorityIn, caller: AdminUser, session: SessionDep) -> PriorityOut:
    await _reject_duplicate_name(session, Priority, body.name, "priority")
    priority = Priority(**body.model_dump())
    session.add(priority)
    await session.flush()
    _audited(
        session,
        "priority",
        priority,
        caller.id,
        "created",
        after=_state(priority, "name", "rank", "color_hex"),
    )
    await session.commit()
    return PriorityOut.model_validate(priority)


@router.patch("/priorities/{priority_id}")
async def update_priority(
    priority_id: uuid.UUID, body: PriorityPatch, caller: AdminUser, session: SessionDep
) -> PriorityOut:
    priority = await _get(session, Priority, priority_id, "Priority")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        await _reject_duplicate_name(
            session, Priority, changes["name"], "priority", exclude=priority_id
        )
    before = _state(priority, "name", "rank", "color_hex")
    for key, value in changes.items():
        setattr(priority, key, value)
    _audited(
        session,
        "priority",
        priority,
        caller.id,
        "updated",
        before=before,
        after=_state(priority, "name", "rank", "color_hex"),
    )
    await session.commit()
    return PriorityOut.model_validate(priority)


@router.delete("/priorities/{priority_id}", status_code=204)
async def delete_priority(
    priority_id: uuid.UUID, caller: AdminUser, session: SessionDep
) -> Response:
    priority = await _get(session, Priority, priority_id, "Priority")
    await _reject_if_referenced(
        session,
        "priority",
        (Ticket.priority_id, priority_id),
        (SlaPolicy.priority_id, priority_id),
        (AiClassificationHistory.predicted_priority_id, priority_id),
        (AiClassificationHistory.corrected_priority_id, priority_id),
    )
    _audited(session, "priority", priority, caller.id, "deleted", before={"name": priority.name})
    await session.delete(priority)
    await session.commit()
    return Response(status_code=204)


# --- SLA policies -----------------------------------------------------------

# A day of minutes is already an unusually generous resolution target; anything
# beyond a fortnight is a typo that silently disables the breach monitor.
Minutes = Annotated[int, Field(ge=1, le=20_160)]


class SlaRuleIn(BaseModel):
    category_id: uuid.UUID | None = None
    priority_id: uuid.UUID
    response_minutes: Minutes
    resolution_minutes: Minutes


class SlaRulePatch(BaseModel):
    category_id: uuid.UUID | None = None
    response_minutes: Minutes | None = None
    resolution_minutes: Minutes | None = None


class SlaRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID | None
    priority_id: uuid.UUID
    response_minutes: int
    resolution_minutes: int
    created_at: datetime
    updated_at: datetime


async def _reject_duplicate_policy(
    session: AsyncSession,
    category_id: uuid.UUID | None,
    priority_id: uuid.UUID,
    exclude: uuid.UUID | None = None,
) -> None:
    """`policy_for` resolves a match with `.limit(1)` and no tie-break beyond
    category specificity, so two rows on the same (category, priority) pair make
    every ticket's deadline a coin flip. Doc 05 has no unique constraint on the
    pair — only an index — so the API is where this is enforced."""
    query = sa.select(SlaPolicy.id).where(
        SlaPolicy.priority_id == priority_id,
        SlaPolicy.category_id.is_(None)
        if category_id is None
        else SlaPolicy.category_id == category_id,
    )
    if exclude:
        query = query.where(SlaPolicy.id != exclude)
    if (await session.execute(query.limit(1))).first():
        raise HTTPException(
            status_code=409,
            detail="An SLA rule already covers that category and priority; edit it instead",
        )


@router.get("/sla-rules")
async def list_sla_rules(caller: AdminUser, session: SessionDep) -> list[SlaRuleOut]:
    # Nulls last: the catch-all default reads naturally at the bottom of the table.
    query = sa.select(SlaPolicy).order_by(
        SlaPolicy.category_id.is_(None), SlaPolicy.created_at.desc()
    )
    return [SlaRuleOut.model_validate(p) for p in (await session.execute(query)).scalars()]


@router.post("/sla-rules", status_code=201)
async def create_sla_rule(body: SlaRuleIn, caller: AdminUser, session: SessionDep) -> SlaRuleOut:
    await _get(session, Priority, body.priority_id, "Priority")
    if body.category_id:
        await _get(session, Category, body.category_id, "Category")
    await _reject_duplicate_policy(session, body.category_id, body.priority_id)
    policy = SlaPolicy(**body.model_dump())
    session.add(policy)
    await session.flush()
    _audited(
        session,
        "sla_policy",
        policy,
        caller.id,
        "created",
        after=_state(
            policy, "category_id", "priority_id", "response_minutes", "resolution_minutes"
        ),
    )
    await session.commit()
    return SlaRuleOut.model_validate(policy)


@router.patch("/sla-rules/{rule_id}")
async def update_sla_rule(
    rule_id: uuid.UUID, body: SlaRulePatch, caller: AdminUser, session: SessionDep
) -> SlaRuleOut:
    policy = await _get(session, SlaPolicy, rule_id, "SLA rule")
    changes = body.model_dump(exclude_unset=True)
    if "category_id" in changes:
        if changes["category_id"]:
            await _get(session, Category, changes["category_id"], "Category")
        await _reject_duplicate_policy(
            session, changes["category_id"], policy.priority_id, exclude=rule_id
        )
    fields = ("category_id", "priority_id", "response_minutes", "resolution_minutes")
    before = _state(policy, *fields)
    for key, value in changes.items():
        setattr(policy, key, value)
    policy.updated_at = datetime.now(UTC)
    # Editing a policy does not retime tickets already running against it —
    # Phase 4 sets due-at columns once, at classification (App Flow §16).
    _audited(
        session,
        "sla_policy",
        policy,
        caller.id,
        "updated",
        before=before,
        after=_state(policy, *fields),
    )
    await session.commit()
    return SlaRuleOut.model_validate(policy)


@router.delete("/sla-rules/{rule_id}", status_code=204)
async def delete_sla_rule(rule_id: uuid.UUID, caller: AdminUser, session: SessionDep) -> Response:
    policy = await _get(session, SlaPolicy, rule_id, "SLA rule")
    # Nothing references sla_policies — tickets carry their own due-at columns —
    # so this one deletes freely.
    _audited(
        session,
        "sla_policy",
        policy,
        caller.id,
        "deleted",
        before=_state(policy, "category_id", "priority_id"),
    )
    await session.delete(policy)
    await session.commit()
    return Response(status_code=204)


# --- Audit log reader (Doc 03 §1, "searchable log of ticket and admin changes") ---


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    before_state: dict | None
    after_state: dict | None
    created_at: datetime


@router.get("/audit-logs")
async def list_audit_logs(
    caller: AdminUser,
    session: SessionDep,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    action: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLogOut]:
    """Read-only by construction: `audit_logs` is an immutable trail (Doc 05,
    Governance), so there is no write, update or delete route to go with this."""
    query = sa.select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id)
    for column, value in (
        (AuditLog.entity_type, entity_type),
        (AuditLog.entity_id, entity_id),
        (AuditLog.actor_id, actor_id),
        (AuditLog.action, action),
    ):
        if value is not None:
            query = query.where(column == value)
    if start:
        query = query.where(AuditLog.created_at >= start)
    if end:
        query = query.where(AuditLog.created_at <= end)
    result = await session.execute(query.limit(limit).offset(offset))
    return [AuditLogOut.model_validate(row) for row in result.scalars()]


@router.get("/audit-logs/entity-types")
async def list_audit_entity_types(caller: AdminUser, session: SessionDep) -> list[str]:
    """Fills the viewer's filter dropdown. The set is whatever has actually been
    logged, not a hardcoded list that drifts as modules add `audit.log` calls."""
    query = sa.select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
    return list((await session.execute(query)).scalars())
