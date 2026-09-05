"""
Append-only audit log writer, used by every module (Architecture §4.1/§10.1, AUDIT-001-003).
Must be called inside the SAME DB transaction as the state change it records.
WRITTEN, NOT EXECUTED.
"""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    actor_id: UUID | None,
    action_type: str,
    target_entity_type: str,
    target_entity_id: UUID,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_id=actor_id,
            action_type=action_type,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            before_state=before_state,
            after_state=after_state,
            reason=reason,
        )
    )
    # No commit here — caller's transaction commits everything atomically (Section 10.1).
