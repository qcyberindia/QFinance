"""users module business logic — this pass only implements the two compliance-
acknowledgment endpoints (API Spec §4.5.1/§4.5.2, CMPL-004/005), which are a
hard prerequisite for `community`'s first-post charter gate (§4.1.2). The
Profile Control Center: `get_my_profile`/`update_my_profile` implement the
member's own profile (GET/PATCH /users/me/profile). The public profile lives
in the `profile` module; the member directory remains unimplemented.
WRITTEN, NOT EXECUTED."""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.config import get_settings
from app.core.errors import NotFound, QFinanceAPIError
from app.modules.auth.models import User
from app.modules.users.models import ComplianceAcknowledgment, Profile

settings = get_settings()

VALID_RISK_DISCLOSURE_CONTEXTS = ("signup", "first_payment")


async def acknowledge_charter(db: AsyncSession, *, user_id: uuid.UUID) -> ComplianceAcknowledgment:
    """CMPL-004. A fresh row per acknowledgment call — not an upsert — per
    Architecture's `compliance_acknowledgments` design (append-only, so which
    document_version a member actually acknowledged is never lost even if the
    Charter text changes later)."""
    ack = ComplianceAcknowledgment(
        id=uuid.uuid4(), user_id=user_id, acknowledgment_type="member_charter",
        document_version=settings.MEMBER_CHARTER_VERSION, acknowledged_at=datetime.now(timezone.utc).replace(tzinfo=None),
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
        document_version=settings.RISK_DISCLOSURE_VERSION, acknowledged_at=datetime.now(timezone.utc).replace(tzinfo=None),
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


# ---------------------------------------------------------------------------
# Own profile (Profile Control Center) — always the session's own user.
# ---------------------------------------------------------------------------

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,30}$")
NAME_MAX = 80
BIO_MAX = 500
EXPERIENCE_LEVELS = ("beginner", "intermediate", "advanced")


async def get_my_profile(db: AsyncSession, *, user: User) -> dict:
    """The member's own profile: public fields plus private account details
    (name, email) that only they can see. Never includes credentials,
    broker data, portfolio data or roles."""
    from app.modules.profile.service import get_activity_summary

    profile = await db.get(Profile, user.id)
    if profile is None:
        raise NotFound("Profile not found.")
    return {
        "username": profile.username,
        "bio": profile.bio,
        "experience_level": profile.experience_level,
        "name": profile.name,
        "email": user.email,
        "email_verified": user.email_verified_at is not None,
        "joined_at": profile.created_at,
        **(await get_activity_summary(db, user_id=user.id)),
    }


async def update_my_profile(db: AsyncSession, *, user: User, changes: dict) -> dict:
    """Partial update of the caller's own profile. Validates every field and
    reports all failures together. Email is not editable here."""
    profile = await db.get(Profile, user.id)
    if profile is None:
        raise NotFound("Profile not found.")

    errors: dict[str, str] = {}
    updates: dict = {}
    if "name" in changes:
        name = (changes["name"] or "").strip()
        if not name or len(name) > NAME_MAX:
            errors["name"] = f"Name must be 1-{NAME_MAX} characters."
        else:
            updates["name"] = name
    if "username" in changes:
        username = (changes["username"] or "").strip()
        if not USERNAME_PATTERN.match(username):
            errors["username"] = "Username must be 3-30 letters, numbers or underscores."
        elif username.lower() != profile.username.lower():
            taken = (await db.execute(
                select(Profile.user_id).where(Profile.username == username, Profile.user_id != user.id)
            )).first()
            if taken:
                errors["username"] = "This username is already taken."
        if "username" not in errors:
            updates["username"] = username
    if "bio" in changes:
        bio = (changes["bio"] or "").strip()
        if len(bio) > BIO_MAX:
            errors["bio"] = f"Bio must be at most {BIO_MAX} characters."
        else:
            updates["bio"] = bio or None
    if "experience_level" in changes:
        level = changes["experience_level"]
        if level is not None and level not in EXPERIENCE_LEVELS:
            errors["experience_level"] = "Choose beginner, intermediate or advanced."
        else:
            updates["experience_level"] = level

    if errors:
        raise QFinanceAPIError("VALIDATION_ERROR", "Please fix the highlighted fields.", 400, fields=errors)

    before = {k: getattr(profile, k) for k in updates if k in ("username",)}
    for key, value in updates.items():
        setattr(profile, key, value)
    if before:
        await write_audit_log(
            db, actor_id=user.id, action_type="profile.username_changed", target_entity_type="profile",
            target_entity_id=user.id, before_state=before, after_state={"username": profile.username},
        )
    await db.commit()
    await db.refresh(profile)
    return await get_my_profile(db, user=user)
