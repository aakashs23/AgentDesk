"""Notification endpoints (Phase 7; TRD §3).

Three concerns: the in-app feed for the current user (`GET /notifications`,
`PATCH /notifications/{id}/read`), that user's channel preferences
(`PATCH /notifications/preferences`), and admin-only template CRUD
(`/notification-templates`, Doc 05 §6 — Admin full CRUD, no one else).
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from app.audit import service as audit
from app.auth.deps import CurrentUser, SessionDep, require_role
from app.models import Notification, NotificationTemplate, User
from app.notifications.templates import CHANNELS, NOTIFICATION_TRIGGERS

router = APIRouter(tags=["notifications"])

AdminUser = Annotated[User, Depends(require_role("admin"))]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID | None
    trigger_type: str
    channel: str
    is_read: bool
    payload: dict | None
    created_at: datetime


class PreferencesPatch(BaseModel):
    # {"sla_warning": {"email": false, "in_app": true}, ...}
    preferences: dict[str, dict[str, bool]]


class TemplateIn(BaseModel):
    trigger_type: str
    channel: str
    subject_template: str | None = None
    body_template: str
    is_active: bool = True


class TemplatePatch(BaseModel):
    subject_template: str | None = None
    body_template: str | None = None
    is_active: bool | None = None


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger_type: str
    channel: str
    subject_template: str | None
    body_template: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


# --- In-app feed ---


@router.get("/notifications")
async def list_notifications(
    caller: CurrentUser,
    session: SessionDep,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[NotificationOut]:
    query = sa.select(Notification).where(
        Notification.user_id == caller.id, Notification.channel == "in_app"
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    query = query.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    return [NotificationOut.model_validate(n) for n in (await session.execute(query)).scalars()]


@router.patch("/notifications/preferences")
async def update_preferences(
    body: PreferencesPatch, caller: CurrentUser, session: SessionDep
) -> dict:
    for trigger, channels in body.preferences.items():
        if trigger not in NOTIFICATION_TRIGGERS:
            raise HTTPException(status_code=422, detail=f"Unknown trigger: {trigger}")
        for channel in channels:
            if channel not in CHANNELS:
                raise HTTPException(status_code=422, detail=f"Unknown channel: {channel}")
    # Merge over existing prefs so a partial patch doesn't wipe untouched triggers.
    merged = dict(caller.notification_preferences or {})
    for trigger, channels in body.preferences.items():
        merged[trigger] = {**merged.get(trigger, {}), **channels}
    caller.notification_preferences = merged
    caller.updated_at = datetime.now(UTC)
    await session.commit()
    return merged


@router.patch("/notifications/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID, caller: CurrentUser, session: SessionDep
) -> NotificationOut:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id != caller.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    await session.commit()
    return NotificationOut.model_validate(notification)


# --- Template CRUD (admin) ---


def _validate_template(trigger_type: str, channel: str) -> None:
    if trigger_type not in NOTIFICATION_TRIGGERS:
        raise HTTPException(status_code=422, detail=f"Unknown trigger_type: {trigger_type}")
    if channel not in CHANNELS:
        raise HTTPException(status_code=422, detail=f"Unknown channel: {channel}")


@router.get("/notification-templates")
async def list_templates(caller: AdminUser, session: SessionDep) -> list[TemplateOut]:
    result = await session.execute(
        sa.select(NotificationTemplate).order_by(
            NotificationTemplate.trigger_type, NotificationTemplate.channel
        )
    )
    return [TemplateOut.model_validate(t) for t in result.scalars()]


@router.post("/notification-templates", status_code=201)
async def create_template(body: TemplateIn, caller: AdminUser, session: SessionDep) -> TemplateOut:
    _validate_template(body.trigger_type, body.channel)
    template = NotificationTemplate(**body.model_dump(), created_by=caller.id)
    session.add(template)
    await session.flush()
    audit.log(
        session,
        "notification_template",
        template.id,
        caller.id,
        "created",
        after={"trigger_type": template.trigger_type, "channel": template.channel},
    )
    await session.commit()
    return TemplateOut.model_validate(template)


@router.patch("/notification-templates/{template_id}")
async def update_template(
    template_id: uuid.UUID, body: TemplatePatch, caller: AdminUser, session: SessionDep
) -> TemplateOut:
    template = await session.get(NotificationTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(template, key, value)
    template.updated_at = datetime.now(UTC)
    audit.log(
        session,
        "notification_template",
        template.id,
        caller.id,
        "updated",
        after={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return TemplateOut.model_validate(template)


@router.delete("/notification-templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID, caller: AdminUser, session: SessionDep
) -> Response:
    template = await session.get(NotificationTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    audit.log(
        session,
        "notification_template",
        template.id,
        caller.id,
        "deleted",
        before={"trigger_type": template.trigger_type, "channel": template.channel},
    )
    await session.delete(template)
    await session.commit()
    return Response(status_code=204)
