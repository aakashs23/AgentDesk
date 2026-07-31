"""Reporting: live dashboard metrics + generated reports (Phase 8; TRD §12).

Dashboard metrics are computed on demand, role-scoped via
`scope_tickets_to_caller`. Reports are generated in the background (so a large
dataset never blocks the request) into an in-process store, then exported to
CSV / XLSX / PDF on demand.

ponytail: the report store is an in-process dict, not a table — Doc 05 has no
`reports` table and the invariants forbid adding one. Fine for the single-worker
prototype; swap for Redis/a table if this ever runs multi-worker.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import scope_tickets_to_caller
from app.models import (
    AiClassificationHistory,
    AiDraftHistory,
    Category,
    Priority,
    Queue,
    Role,
    Ticket,
    User,
)
from app.tickets.service import STAFF

logger = logging.getLogger("agentdesk")

OPEN_STATUSES_EXCLUDED = ("closed", "resolved")  # everything else counts as "open"


def _scope(caller: User, role: str):
    return scope_tickets_to_caller(caller, role, Ticket, Queue, User)


def _scoped_ticket_ids(caller: User, role: str):
    return sa.select(Ticket.id).where(_scope(caller, role)).subquery()


# --- Live dashboard ---


async def dashboard_metrics(session: AsyncSession, caller: User, role: str) -> dict:
    scope = _scope(caller, role)
    open_count = (
        await session.execute(
            sa.select(sa.func.count())
            .select_from(Ticket)
            .where(scope, Ticket.status.notin_(OPEN_STATUSES_EXCLUDED))
        )
    ).scalar_one()

    avg_resolution_seconds = (
        await session.execute(
            sa.select(
                sa.func.avg(sa.func.extract("epoch", Ticket.resolved_at - Ticket.created_at))
            ).where(scope, Ticket.resolved_at.isnot(None))
        )
    ).scalar()

    sla = (
        await session.execute(
            sa.select(
                sa.func.count()
                .filter(Ticket.resolved_at.isnot(None), Ticket.resolution_due_at.isnot(None))
                .label("resolved_with_target"),
                sa.func.count()
                .filter(
                    Ticket.resolved_at.isnot(None),
                    Ticket.resolution_due_at.isnot(None),
                    Ticket.resolved_at <= Ticket.resolution_due_at,
                )
                .label("met"),
            ).where(scope)
        )
    ).one()
    compliance_rate = (sla.met / sla.resolved_with_target) if sla.resolved_with_target else None

    workload_rows = (
        await session.execute(
            sa.select(Ticket.assignee_id, User.full_name, sa.func.count().label("open"))
            .join(User, User.id == Ticket.assignee_id)
            # Assignment now refuses non-staff, but rows written before that (or
            # by a direct DB edit) must not show a requester as an agent.
            .join(Role, Role.id == User.role_id)
            .where(scope, Ticket.status.notin_(OPEN_STATUSES_EXCLUDED), Role.name.in_(STAFF))
            .group_by(Ticket.assignee_id, User.full_name)
            .order_by(sa.desc("open"))
        )
    ).all()

    return {
        "open_ticket_count": open_count,
        "avg_resolution_seconds": float(avg_resolution_seconds) if avg_resolution_seconds else None,
        "sla_compliance_rate": round(compliance_rate, 4) if compliance_rate is not None else None,
        "agent_workload": [
            {"assignee_id": str(a), "full_name": name, "open_tickets": n}
            for a, name, n in workload_rows
        ],
    }


# --- Report generators (columns, rows) ---


def _range(query, column, start: datetime | None, end: datetime | None):
    if start:
        query = query.where(column >= start)
    if end:
        query = query.where(column <= end)
    return query


async def _agent_productivity(session, ids, start, end):
    q = _range(
        sa.select(
            Ticket.assignee_id,
            User.full_name,
            sa.func.count().label("resolved"),
            sa.func.avg(sa.func.extract("epoch", Ticket.resolved_at - Ticket.created_at)).label(
                "avg_handle_seconds"
            ),
        )
        .join(User, User.id == Ticket.assignee_id)
        .where(Ticket.id.in_(sa.select(ids.c.id)), Ticket.resolved_at.isnot(None)),
        Ticket.resolved_at,
        start,
        end,
    ).group_by(Ticket.assignee_id, User.full_name)
    rows = (await session.execute(q)).all()
    return ["assignee_id", "full_name", "resolved", "avg_handle_seconds"], [
        {
            "assignee_id": str(a),
            "full_name": name,
            "resolved": n,
            "avg_handle_seconds": round(float(avg), 1) if avg else None,
        }
        for a, name, n, avg in rows
    ]


async def _sla_compliance(session, ids, start, end):
    q = _range(
        sa.select(
            Priority.name,
            sa.func.count().filter(Ticket.resolution_due_at.isnot(None)).label("total"),
            sa.func.count()
            .filter(
                Ticket.resolved_at.isnot(None),
                Ticket.resolution_due_at.isnot(None),
                Ticket.resolved_at <= Ticket.resolution_due_at,
            )
            .label("met"),
        )
        .join(Priority, Priority.id == Ticket.priority_id, isouter=True)
        .where(Ticket.id.in_(sa.select(ids.c.id))),
        Ticket.created_at,
        start,
        end,
    ).group_by(Priority.name)
    rows = (await session.execute(q)).all()
    return ["priority", "total", "met", "compliance_rate"], [
        {
            "priority": name,
            "total": total,
            "met": met,
            "compliance_rate": round(met / total, 4) if total else None,
        }
        for name, total, met in rows
    ]


async def _ticket_trends(session, ids, start, end):
    day = sa.func.date_trunc("day", Ticket.created_at).label("day")
    q = (
        _range(
            sa.select(day, sa.func.count().label("count")).where(
                Ticket.id.in_(sa.select(ids.c.id))
            ),
            Ticket.created_at,
            start,
            end,
        )
        .group_by(day)
        .order_by(day)
    )
    rows = (await session.execute(q)).all()
    return ["day", "count"], [{"day": d.isoformat(), "count": n} for d, n in rows]


async def _category_analytics(session, ids, start, end):
    q = (
        _range(
            sa.select(Category.name, sa.func.count().label("count"))
            .select_from(Ticket)  # or the lone Category column infers the FROM
            .join(Category, Category.id == Ticket.category_id, isouter=True)
            .where(Ticket.id.in_(sa.select(ids.c.id))),
            Ticket.created_at,
            start,
            end,
        )
        .group_by(Category.name)
        .order_by(sa.desc("count"))
    )
    rows = (await session.execute(q)).all()
    return ["category", "count"], [{"category": name, "count": n} for name, n in rows]


async def _ai_performance(session, ids, start, end):
    cls = (
        await session.execute(
            _range(
                sa.select(
                    sa.func.count().label("total"),
                    sa.func.count()
                    .filter(AiClassificationHistory.was_overridden.is_(True))
                    .label("overridden"),
                    sa.func.count()
                    .filter(
                        sa.or_(
                            AiClassificationHistory.corrected_category_id.isnot(None),
                            AiClassificationHistory.corrected_priority_id.isnot(None),
                        )
                    )
                    .label("corrected"),
                ).where(AiClassificationHistory.ticket_id.in_(sa.select(ids.c.id))),
                AiClassificationHistory.created_at,
                start,
                end,
            )
        )
    ).one()

    draft_rows = (
        await session.execute(
            _range(
                sa.select(AiDraftHistory.review_status, sa.func.count().label("n")).where(
                    AiDraftHistory.ticket_id.in_(sa.select(ids.c.id))
                ),
                AiDraftHistory.created_at,
                start,
                end,
            ).group_by(AiDraftHistory.review_status)
        )
    ).all()
    drafts = {status: n for status, n in draft_rows}
    draft_total = sum(drafts.values())

    columns = ["metric", "value"]
    rows = [
        {"metric": "classifications_total", "value": cls.total},
        {
            "metric": "classification_accuracy",
            "value": round(1 - cls.corrected / cls.total, 4) if cls.total else None,
        },
        {
            "metric": "auto_routing_acceptance_rate",
            "value": round(1 - cls.overridden / cls.total, 4) if cls.total else None,
        },
        {"metric": "drafts_total", "value": draft_total},
        {"metric": "drafts_approved", "value": drafts.get("approved", 0)},
        {"metric": "drafts_edited", "value": drafts.get("edited", 0)},
        {"metric": "drafts_rejected", "value": drafts.get("rejected", 0)},
        {
            "metric": "draft_approval_rate",
            "value": round((drafts.get("approved", 0) + drafts.get("edited", 0)) / draft_total, 4)
            if draft_total
            else None,
        },
    ]
    return columns, rows


async def _ai_performance_trend(session, ids, start, end):
    """The same numbers as `_ai_performance`, one row per day.

    Doc 06's Phase 12 asks for the AI Performance Monitor's rates "over time".
    That is this generator rather than a new endpoint: it inherits the existing
    report plumbing — role scoping, background generation, CSV/XLSX/PDF export —
    and the monitor screen charts the rows it gets back.

    Classifications and drafts are counted in separate queries and joined by day
    in Python: a SQL join between them double-counts, because one ticket can
    carry several drafts against a single classification.
    """
    day = sa.func.date_trunc("day", AiClassificationHistory.created_at).label("day")
    cls_rows = (
        await session.execute(
            _range(
                sa.select(
                    day,
                    sa.func.count().label("total"),
                    sa.func.count()
                    .filter(AiClassificationHistory.was_overridden.is_(True))
                    .label("overridden"),
                ).where(AiClassificationHistory.ticket_id.in_(sa.select(ids.c.id))),
                AiClassificationHistory.created_at,
                start,
                end,
            )
            .group_by(day)
            .order_by(day)
        )
    ).all()

    draft_day = sa.func.date_trunc("day", AiDraftHistory.created_at).label("day")
    draft_rows = (
        await session.execute(
            _range(
                sa.select(
                    draft_day,
                    sa.func.count().label("total"),
                    sa.func.count()
                    .filter(AiDraftHistory.review_status.in_(("approved", "edited")))
                    .label("accepted"),
                ).where(AiDraftHistory.ticket_id.in_(sa.select(ids.c.id))),
                AiDraftHistory.created_at,
                start,
                end,
            )
            .group_by(draft_day)
            .order_by(draft_day)
        )
    ).all()
    drafts = {d: (total, accepted) for d, total, accepted in draft_rows}

    columns = [
        "day",
        "classifications",
        "accepted_classifications",
        "auto_routing_acceptance_rate",
        "drafts",
        "draft_approval_rate",
    ]
    rows = []
    for d in sorted({d for d, *_ in cls_rows} | set(drafts)):
        total, overridden = next(((t, o) for day_, t, o in cls_rows if day_ == d), (0, 0))
        draft_total, accepted = drafts.get(d, (0, 0))
        rows.append(
            {
                "day": d.isoformat(),
                "classifications": total,
                "accepted_classifications": total - overridden,
                "auto_routing_acceptance_rate": round(1 - overridden / total, 4) if total else None,
                "drafts": draft_total,
                "draft_approval_rate": round(accepted / draft_total, 4) if draft_total else None,
            }
        )
    return columns, rows


GENERATORS = {
    "agent_productivity": _agent_productivity,
    "sla_compliance": _sla_compliance,
    "ticket_trends": _ticket_trends,
    "category_analytics": _category_analytics,
    "ai_performance": _ai_performance,
    "ai_performance_trend": _ai_performance_trend,
}


# --- In-process report store + background generation ---


@dataclass
class Report:
    id: uuid.UUID
    report_type: str
    status: str = "pending"  # pending / ready / failed
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    error: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


_REPORTS: dict[uuid.UUID, Report] = {}


def create_report(report_type: str, created_by: uuid.UUID) -> Report:
    report = Report(id=uuid.uuid4(), report_type=report_type, created_by=created_by)
    _REPORTS[report.id] = report
    return report


def get_report(report_id: uuid.UUID) -> Report | None:
    return _REPORTS.get(report_id)


async def generate(
    report_id: uuid.UUID,
    report_type: str,
    caller: User,
    role: str,
    start: datetime | None,
    end: datetime | None,
) -> None:
    """Run a report generator in its own session (invoked as a background task)."""
    from app.db import _session_factory

    report = _REPORTS[report_id]
    try:
        async with _session_factory() as session:
            ids = _scoped_ticket_ids(caller, role)
            report.columns, report.rows = await GENERATORS[report_type](session, ids, start, end)
        report.status = "ready"
    except Exception:  # store the failure instead of losing it in a background task
        logger.exception("report %s (%s) failed to generate", report_id, report_type)
        report.status = "failed"
        # `str(exc)` here reaches the client verbatim — ORM internals, memory
        # addresses and all. The detail belongs in the log, not the response.
        report.error = "Report generation failed"
