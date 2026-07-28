"""Reporting endpoints (Phase 8; TRD §12): live dashboard metrics and
generate/poll/export of reports. Staff-only; every query is role-scoped in the
service layer via `scope_tickets_to_caller`."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from app.auth.deps import SessionDep, require_role, role_name
from app.models import User
from app.reporting import export, service

router = APIRouter(tags=["reporting"])

StaffUser = Annotated[User, Depends(require_role("agent", "team_lead", "admin"))]


@router.get("/dashboard/metrics")
async def dashboard_metrics(caller: StaffUser, session: SessionDep) -> dict:
    role = await role_name(session, caller.role_id)
    return await service.dashboard_metrics(session, caller, role)


class ReportRequest(BaseModel):
    report_type: str
    start_date: datetime | None = None
    end_date: datetime | None = None


class ReportOut(BaseModel):
    id: uuid.UUID
    report_type: str
    status: str
    columns: list[str]
    rows: list[dict]
    error: str | None


def _to_out(report: service.Report, rows: list[dict]) -> ReportOut:
    return ReportOut(
        id=report.id,
        report_type=report.report_type,
        status=report.status,
        columns=report.columns,
        rows=rows,
        error=report.error,
    )


@router.post("/reports/generate", status_code=202)
async def generate_report(
    body: ReportRequest,
    caller: StaffUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> ReportOut:
    if body.report_type not in service.GENERATORS:
        raise HTTPException(status_code=422, detail=f"Unknown report_type: {body.report_type}")
    role = await role_name(session, caller.role_id)
    report = service.create_report(body.report_type, caller.id)
    # Generated after the response so a large dataset never blocks the request.
    background_tasks.add_task(
        service.generate, report.id, body.report_type, caller, role, body.start_date, body.end_date
    )
    return _to_out(report, [])


def _owned_report(report_id: uuid.UUID, caller: User) -> service.Report:
    report = service.get_report(report_id)
    if report is None or report.created_by != caller.id:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/{report_id}")
async def get_report(
    report_id: uuid.UUID,
    caller: StaffUser,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReportOut:
    report = _owned_report(report_id, caller)
    return _to_out(report, report.rows[offset : offset + limit])


@router.get("/reports/{report_id}/export")
async def export_report(
    report_id: uuid.UUID,
    caller: StaffUser,
    format: Annotated[str, Query(pattern="^(csv|xlsx|pdf)$")] = "csv",
) -> Response:
    report = _owned_report(report_id, caller)
    if report.status != "ready":
        raise HTTPException(status_code=409, detail=f"Report is {report.status}, not ready")
    content = export.render(format, report.columns, report.rows)
    filename = f"{report.report_type}.{format}"
    return Response(
        content=content,
        media_type=export.MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
