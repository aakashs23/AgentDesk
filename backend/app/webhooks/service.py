"""Outbound webhooks (Phase 7; Backend Schema Doc 05 §10).

Registration lives in the ORM; `dispatch(event_type, payload)` fans a domain
event out to every active webhook registered for it. Each payload is HMAC-SHA256
signed with the webhook's own `secret`; every attempt — success or failure — is
recorded in `webhook_deliveries`, with exponential backoff between retries.

Secrets are stored encrypted at rest (Doc 05 Sensitive Fields) via Fernet, keyed
by `WEBHOOK_SECRET_ENCRYPTION_KEY`; decrypted only to sign an outgoing payload.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime
from functools import lru_cache

import httpx
import sqlalchemy as sa
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Webhook, WebhookDelivery
from app.workflow.automation import TRIGGERS

logger = logging.getLogger("agentdesk")

# Webhook event vocabulary is the shared trigger set (Doc 05 §10 — one vocabulary
# across webhooks, automation, notifications). Only events we actually dispatch.
WEBHOOK_EVENTS = TRIGGERS

MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_SECONDS = 1

# Hold references to in-flight delivery tasks so the event loop doesn't GC them
# mid-flight (asyncio.create_task keeps only a weak reference).
_tasks: set[asyncio.Task] = set()


@lru_cache
def _fernet() -> Fernet:
    raw = get_settings().webhook_secret_encryption_key
    if not raw:
        # ponytail: fixed dev secret so encrypt/decrypt survives a restart without
        # config. Set WEBHOOK_SECRET_ENCRYPTION_KEY in production.
        logger.warning("WEBHOOK_SECRET_ENCRYPTION_KEY unset — using an insecure dev key")
        raw = "agentdesk-dev"
    # Derive a valid Fernet key from the configured secret so any string works
    # (hex, passphrase, or a real key) rather than requiring exact key formatting.
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def _deliver_one(
    session: AsyncSession, webhook: Webhook, event_type: str, payload: dict
) -> None:
    secret = decrypt_secret(webhook.secret)
    body = json.dumps(payload, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "X-AgentDesk-Event": event_type,
        "X-AgentDesk-Signature": sign(secret, body),
    }
    backoff = _INITIAL_BACKOFF_SECONDS
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status: int | None = None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(webhook.target_url, content=body, headers=headers)
                status = resp.status_code
        except httpx.HTTPError as exc:
            logger.warning("webhook %s POST failed (attempt %d): %s", webhook.id, attempt, exc)
        delivered = status is not None and 200 <= status < 300
        session.add(
            WebhookDelivery(
                webhook_id=webhook.id,
                event_type=event_type,
                payload=payload,
                response_status=status,
                attempt_count=attempt,
                delivered_at=datetime.now(UTC) if delivered else None,
            )
        )
        if delivered:
            return
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(backoff)
            backoff *= 2


async def _run_dispatch(event_type: str, payload: dict) -> None:
    from app.db import _session_factory

    try:
        async with _session_factory() as session:
            result = await session.execute(
                sa.select(Webhook).where(
                    Webhook.event_type == event_type, Webhook.is_active.is_(True)
                )
            )
            for webhook in result.scalars():
                await _deliver_one(session, webhook, event_type, payload)
            await session.commit()
    except Exception:
        logger.exception("webhook dispatch for %s failed", event_type)


def dispatch(event_type: str, payload: dict) -> None:
    """Fire-and-forget outbound delivery, decoupled from the request transaction.

    ponytail: an in-process background task, not a durable queue — fine for the
    prototype; swap for a real job runner if deliveries must survive a restart.
    """
    task = asyncio.create_task(_run_dispatch(event_type, payload))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def ticket_payload(event_type: str, ticket) -> dict:
    return {
        "event": event_type,
        "ticket_id": str(ticket.id),
        "display_id": f"AGT-{ticket.display_id}",
        "subject": ticket.subject,
        "status": ticket.status,
        "priority_id": str(ticket.priority_id) if ticket.priority_id else None,
        "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
    }


def new_secret() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex
