"""users module business logic — this pass only implements the two compliance-
acknowledgment endpoints (API Spec §4.5.1/§4.5.2, CMPL-004/005), which are a
hard prerequisite for `community`'s first-post charter gate (§4.1.2). The
broader `users` module (§2: GET/PATCH /users/me, public profile, directory)
remains unimplemented — flagged explicitly in work_memory.md, not silently
left looking done because this file now exists.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.users.models import ComplianceAcknowledgment

settings = get_settings()

VALID_RISK_DISCLOSURE_CONTEXTS = ("signup", "first_payment")


async def acknowledge_charter(db: AsyncSession, *, user_id: uuid.UUID) -> ComplianceAcknowledgment:
    """CMPL-004. A fresh row per acknowledgment call — not an upsert — per
    Architecture's `compliance_acknowledgments` design (append-only, so which
    document_version a member actually acknowledged is never lost even if the
    Charter text changes later)."""
    ack = ComplianceAcknowledgment(
        id=uuid.uuid4(), user_id=user_id, acknowledgment_type="member_charter",
        document_version=settings.MEMBER_CHARTER_VERSION, acknowledged_at=datetime.now(timezone.utc),
    )
    db.add(ack)
    await db.commit()
    return ack


async def acknowledge_risk_disclosure(db: AsyncSession, *, user_id: uuid.UUID, context: str) -> ComplianceAcknowledgment:
    """CMPL-005. `context` is accepted and validated but not stored as a
    separate column — Database Schema §8A's `compliance_acknowledgments` has
    no `context` field; multiple `risk_disclosure` rows per user are expected
    and correct (one per required occasion: signup, first payment), and the
    row's `acknowledged_at` timestamp combined with call-site sequencing is
    sufficient for this MVP's audit purpose. Rejecting an invalid context
    value here (rather than accepting any string) keeps the caller honest
    about which of the two PRD-required occasions this is."""
    from app.core.errors import QFinanceAPIError
    if context not in VALID_RISK_DISCLOSURE_CONTEXTS:
        raise QFinanceAPIError(
            "INVALID_ACKNOWLEDGMENT_CONTEXT",
            f"context must be one of {VALID_RISK_DISCLOSURE_CONTEXTS}.", 400,
        )
    ack = ComplianceAcknowledgment(
        id=uuid.uuid4(), user_id=user_id, acknowledgment_type="risk_disclosure",
        document_version=settings.RISK_DISCLOSURE_VERSION, acknowledged_at=datetime.now(timezone.utc),
    )
    db.add(ack)
    await db.commit()
    return ack


async def has_acknowledged_current_charter(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
    """Used by `community.service`'s CMPL-004 first-post gate (§4.1.2) — checks
    for a row matching the *current* `MEMBER_CHARTER_VERSION`, not just any
    past acknowledgment, so a Charter text update correctly requires members
    to re-acknowledge before their next post."""
    result = await db.execute(
        select(ComplianceAcknowledgment.id).where(
            ComplianceAcknowledgment.user_id == user_id,
            ComplianceAcknowledgment.acknowledgment_type == "member_charter",
            ComplianceAcknowledgment.document_version == settings.MEMBER_CHARTER_VERSION,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None
