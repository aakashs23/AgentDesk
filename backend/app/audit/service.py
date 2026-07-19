"""Immutable polymorphic audit trail (Document 05, Governance).

Every mutating domain action calls `log()`; status changes additionally write
`ticket_status_history` via the workflow engine — two tables, two purposes.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


def log(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    action: str,
    before: dict | None = None,
    after: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor_id,
            action=action,
            before_state=before,
            after_state=after,
        )
    )
