"""Membership business logic — API Specification V1 §3.1/§3.3 (MEM-001/002/005-007,
OD-06/22). Owns `plans`/`subscriptions` — per Architecture §4.4, other modules
(billing) call into this service rather than writing these tables directly.

ENTITLEMENT SYNC (fixed this pass — see work_memory.md): `require_role("MEMBER")`,
used by `research`/`companies`/etc., checks the *stored* `profiles.role_grants`
array (core/deps.py), not a live subscription query. Before this fix,
`activate_subscription` updated `subscriptions` but never granted `MEMBER` on
`profiles.role_grants` — meaning a member who successfully paid would still be
denied every MEMBER-gated endpoint. This is now corrected: `activate_subscription`
grants `MEMBER` (idempotently — a re-activation/renewal for an existing member is a
no-op on the array), and `expire_overdue_subscriptions` revokes it exactly when the
spec says access should end (grace-period expiry, or a self-canceled subscription
reaching the end of its already-paid period) — never earlier, so MEM-007's "access
continues to end of paid period after cancellation" still holds: canceling alone
never touches `role_grants`.

NOTE on notifications (flagged, not silently worked around): API Spec §3.3.1's
"subscription_change" case is one of `notifications.type`'s CHECK-constrained values
(Database Schema §21), but the `notifications` module itself is not yet implemented
(work_memory.md Part H step 4 places it after community/moderation/watchlist). Rather
than either (a) inventing the notifications module ahead of its scheduled phase, or
(b) silently skipping the audit trail entirely, subscription-state changes are recorded
via the existing, already-built `audit_logs` mechanism instead — Part B.5 of
work_memory.md explicitly lists "subscription events" as within `audit_logs`' scope,
so this is a real, already-approved audit path, not an invented substitute. The
in-app notification itself remains a genuine gap until the `notifications` module
exists — tracked here and in work_memory.md, not hidden.

WRITTEN, NOT EXECUTED — no real database has been reached in this session.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import NotFound
from app.modules.membership.models import Plan, Subscription
from app.modules.users.models import Profile

GRACE_PERIOD_DAYS = 7  # OD-06


def _grant_member_role(profile: Profile) -> None:
    """Idempotent — reassigns the whole list (not .append()) since plain
    ARRAY(String) columns don't get SQLAlchemy's in-place mutation tracking
    without an explicit MutableList wrapper, which this schema doesn't use."""
    if "MEMBER" not in profile.role_grants:
        profile.role_grants = [*profile.role_grants, "MEMBER"]


def _revoke_member_role(profile: Profile) -> None:
    """Removes only the MEMBER grant — MODERATOR/REVIEWER/ADMIN/SUPER_ADMIN grants
    are untouched, since those are independent additive grants (OD-05), not tied to
    Core billing status."""
    if "MEMBER" in profile.role_grants:
        profile.role_grants = [r for r in profile.role_grants if r != "MEMBER"]


async def get_plans(db: AsyncSession) -> list[Plan]:
    """MEM-001/002. Always exactly 2 active rows, enforced by the `plans.code` CHECK
    constraint at the DB layer (Database Schema §3) — this just reads it."""
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_paise))
    return list(result.scalars().all())


async def get_plan_by_code(db: AsyncSession, code: str) -> Plan:
    result = await db.execute(select(Plan).where(Plan.code == code))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise NotFound(f"No such plan: {code}")
    return plan


async def get_current_subscription(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    """The most recent subscription row for this user, if any. A user with no row at
    all is implicitly FREE — not an error state (API Spec §3.1.2's explicit rule)."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user_id).order_by(Subscription.created_at.desc())
    )
    return result.scalars().first()


async def get_my_membership(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """API Spec §3.1.2, extended by API Spec V2 §8 (C.2) with
    `available_credit_paise`/`effective_next_period_price_paise` — additive
    fields, existing consumers of this dict that don't know about them are
    unaffected. Deferred import (not at module top) to avoid `membership`
    and `contributions` forming an import-time coupling neither module
    otherwise needs — `contributions` never imports `membership`."""
    from app.modules.contributions import service as contributions_service

    subscription = await get_current_subscription(db, user_id)
    if subscription is None:
        available_credit_paise, effective_price_paise = await contributions_service.calculate_effective_premium_price_paise(
            db, user_id=user_id, plan_price_paise=0,
        )
        return {
            "plan_code": "FREE",
            "status": "active",
            "current_period_end": None,
            "grace_period_ends_at": None,
            "canceled_at": None,
            "available_credit_paise": available_credit_paise,
            "effective_next_period_price_paise": effective_price_paise,
        }
    plan = await db.get(Plan, subscription.plan_id)
    plan_price = plan.price_paise if plan else 0
    available_credit_paise, effective_price_paise = await contributions_service.calculate_effective_premium_price_paise(
        db, user_id=user_id, plan_price_paise=plan_price,
    )
    return {
        "plan_code": plan.code if plan else "FREE",
        "status": subscription.status,
        "current_period_end": subscription.current_period_end,
        "grace_period_ends_at": subscription.grace_period_ends_at,
        "canceled_at": subscription.canceled_at,
        "available_credit_paise": available_credit_paise,
        "effective_next_period_price_paise": effective_price_paise,
    }


async def activate_subscription(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    plan_code: str,
    current_period_start: datetime,
    current_period_end: datetime,
    gateway_subscription_id: str | None = None,
) -> Subscription:
    """Called by `billing.service` on a confirmed `payment.captured` webhook — this
    module owns the write, per Architecture §4.4's service-interface boundary (billing
    never writes to `subscriptions` directly). Renews in place if the user already has
    an active/past_due row (avoids an unbounded row-per-renewal history that the schema
    doesn't require); otherwise inserts a new row. Does NOT commit — caller (billing's
    webhook handler) commits once, atomically with the `payments`/`invoices` writes,
    per API Spec §3.2.2's single-transaction requirement."""
    plan = await get_plan_by_code(db, plan_code)
    existing = await get_current_subscription(db, user_id)

    if existing is not None and existing.status in ("active", "past_due"):
        existing.status = "active"
        existing.current_period_start = current_period_start
        existing.current_period_end = current_period_end
        existing.grace_period_ends_at = None
        existing.gateway_subscription_id = gateway_subscription_id or existing.gateway_subscription_id
        subscription = existing
    else:
        subscription = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            plan_id=plan.id,
            status="active",
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            gateway_subscription_id=gateway_subscription_id,
        )
        db.add(subscription)

    # Entitlement sync (the fix described in this file's module docstring) — only
    # for the CORE plan; a FREE-plan "activation" is not a real code path today
    # (billing only ever calls this for CORE per billing/service.py) but the guard
    # is explicit rather than assumed.
    if plan.code == "CORE":
        profile = await db.get(Profile, user_id)
        if profile is not None:
            _grant_member_role(profile)

    await db.flush()
    return subscription


async def cancel_subscription(db: AsyncSession, *, actor_id: uuid.UUID) -> Subscription:
    """API Spec §3.3.1 (MEM-007). `current_period_end` is deliberately left untouched
    — access is computed at read time (Architecture §9), no immediate revocation."""
    subscription = await get_current_subscription(db, actor_id)
    if subscription is None or subscription.status not in ("active", "past_due"):
        raise NotFound("No active subscription to cancel.")

    before = {"status": subscription.status, "canceled_at": None}
    subscription.status = "canceled"
    subscription.canceled_at = datetime.now(timezone.utc)

    await write_audit_log(
        db, actor_id=actor_id, action_type="subscription.cancel",
        target_entity_type="subscription", target_entity_id=subscription.id,
        before_state=before, after_state={"status": "canceled", "canceled_at": subscription.canceled_at.isoformat()},
    )
    await db.commit()
    return subscription


async def mark_past_due(db: AsyncSession, *, subscription_id: uuid.UUID) -> Subscription:
    """OD-06 — called by billing on a RENEWAL payment failure (an existing active
    subscription whose next charge failed), starting the 7-day grace period. Not
    called for a first-ever-payment failure (no subscription row exists yet in that
    case — see billing/service.py's flagged, separate gap for that path). Does not
    touch `role_grants` — the member keeps MEMBER access through the entire grace
    period, matching OD-06's "access retained" step; only actual expiry revokes it.
    """
    subscription = await db.get(Subscription, subscription_id)
    if subscription is None:
        raise NotFound("Subscription not found.")
    before = {"status": subscription.status, "grace_period_ends_at": None}
    subscription.status = "past_due"
    subscription.grace_period_ends_at = datetime.now(timezone.utc) + timedelta(days=GRACE_PERIOD_DAYS)
    await write_audit_log(
        db, actor_id=None, action_type="subscription.payment_failed_grace_started",
        target_entity_type="subscription", target_entity_id=subscription.id,
        before_state=before,
        after_state={"status": "past_due", "grace_period_ends_at": subscription.grace_period_ends_at.isoformat()},
        reason="Renewal payment failed; 7-day grace period started (OD-06).",
    )
    await db.flush()
    return subscription


async def expire_overdue_subscriptions(db: AsyncSession) -> int:
    """MEM-006/OD-06 — the grace-period downgrade job (API Spec §3.3, "internal
    scheduled job", not an HTTP endpoint). Handles BOTH ways a subscription's paid
    access legitimately ends in this MVP:
      (a) `status='past_due'` and the 7-day grace period has elapsed (OD-06's
          fail→retry→access-retained→downgrade sequence), or
      (b) `status='canceled'` (self-cancellation, MEM-007) and `current_period_end`
          has now passed — access was correctly retained until this point, per
          MEM-007's "access to end of paid period", and now genuinely ends.
    Both cases: sets `status='expired'` and revokes the `MEMBER` role grant (the
    concrete "downgrade to FREE" action — case (a) was previously implemented
    without this revocation, a real gap fixed this pass). Content is never deleted
    (no cascading delete path exists in this module). Returns the number of
    subscriptions downgraded. Caller is responsible for actually scheduling this
    (e.g., a daily cron/arq job per Architecture AD-07) — this function only
    implements the logic, it does not itself run on a timer.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Subscription).where(
            ((Subscription.status == "past_due") & (Subscription.grace_period_ends_at < now))
            | ((Subscription.status == "canceled") & (Subscription.current_period_end < now))
        )
    )
    overdue = list(result.scalars().all())

    for subscription in overdue:
        await write_audit_log(
            db, actor_id=None, action_type="subscription.grace_period_expired",
            target_entity_type="subscription", target_entity_id=subscription.id,
            before_state={"status": subscription.status}, after_state={"status": "expired"},
            reason="Grace period elapsed without payment, or canceled subscription reached period end (MEM-006/007).",
        )
        subscription.status = "expired"
        profile = await db.get(Profile, subscription.user_id)
        if profile is not None:
            _revoke_member_role(profile)

    if overdue:
        await db.commit()
    return len(overdue)
