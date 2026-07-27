"""Webhook registration + delivery-history endpoints (TRD §3; Doc 05 §10).

Admin-only per the RBAC matrix (Doc 05 §6). The plaintext `secret` is returned
only once, in the create response, so the receiver can be configured to verify
signatures; it is never echoed back on reads.
"""

import uuid
from datetime import datetime
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict

from app.audit import service as audit
from app.auth.deps import SessionDep, require_role
from app.models import User, Webhook, WebhookDelivery
from app.webhooks import service

router = APIRouter(tags=["webhooks"])

AdminUser = Annotated[User, Depends(require_role("admin"))]


class WebhookIn(BaseModel):
    event_type: str
    target_url: str
    secret: str | None = None  # generated if omitted
    is_active: bool = True


class WebhookPatch(BaseModel):
    event_type: str | None = None
    target_url: str | None = None
    is_active: bool | None = None


class WebhookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_type: str
    target_url: str
    is_active: bool
    created_by: uuid.UUID
    created_at: datetime


class WebhookCreatedOut(WebhookOut):
    secret: str  # shown once, at creation, so the receiver can verify signatures


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    webhook_id: uuid.UUID
    event_type: str
    response_status: int | None
    attempt_count: int
    delivered_at: datetime | None
    created_at: datetime


def _validate_event(event_type: str | None) -> None:
    if event_type is not None and event_type not in service.WEBHOOK_EVENTS:
        raise HTTPException(status_code=422, detail=f"Unknown event_type: {event_type}")


async def _get_webhook(session, webhook_id: uuid.UUID) -> Webhook:
    webhook = await session.get(Webhook, webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@router.get("/webhooks")
async def list_webhooks(caller: AdminUser, session: SessionDep) -> list[WebhookOut]:
    result = await session.execute(sa.select(Webhook).order_by(Webhook.created_at.desc()))
    return [WebhookOut.model_validate(w) for w in result.scalars()]


@router.post("/webhooks", status_code=201)
async def create_webhook(
    body: WebhookIn, caller: AdminUser, session: SessionDep
) -> WebhookCreatedOut:
    _validate_event(body.event_type)
    secret = body.secret or service.new_secret()
    webhook = Webhook(
        event_type=body.event_type,
        target_url=body.target_url,
        secret=service.encrypt_secret(secret),
        is_active=body.is_active,
        created_by=caller.id,
    )
    session.add(webhook)
    await session.flush()
    audit.log(
        session,
        "webhook",
        webhook.id,
        caller.id,
        "created",
        after={"event_type": webhook.event_type, "target_url": webhook.target_url},
    )
    await session.commit()
    out = WebhookCreatedOut.model_validate(webhook)
    out.secret = secret
    return out


@router.patch("/webhooks/{webhook_id}")
async def update_webhook(
    webhook_id: uuid.UUID, body: WebhookPatch, caller: AdminUser, session: SessionDep
) -> WebhookOut:
    webhook = await _get_webhook(session, webhook_id)
    changes = body.model_dump(exclude_unset=True)
    _validate_event(changes.get("event_type"))
    for key, value in changes.items():
        setattr(webhook, key, value)
    audit.log(
        session,
        "webhook",
        webhook.id,
        caller.id,
        "updated",
        after={k: str(v) for k, v in changes.items()},
    )
    await session.commit()
    return WebhookOut.model_validate(webhook)


@router.delete("/webhooks/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: uuid.UUID, caller: AdminUser, session: SessionDep) -> Response:
    webhook = await _get_webhook(session, webhook_id)
    await session.execute(
        sa.delete(WebhookDelivery).where(WebhookDelivery.webhook_id == webhook_id)
    )
    audit.log(
        session,
        "webhook",
        webhook.id,
        caller.id,
        "deleted",
        before={"target_url": webhook.target_url},
    )
    await session.delete(webhook)
    await session.commit()
    return Response(status_code=204)


@router.get("/webhooks/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: uuid.UUID,
    caller: AdminUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DeliveryOut]:
    await _get_webhook(session, webhook_id)
    result = await session.execute(
        sa.select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return [DeliveryOut.model_validate(d) for d in result.scalars()]
