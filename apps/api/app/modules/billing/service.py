"""Billing business logic — API Specification V1 §3.2/§3.4 (PAY-001-006, ERR-003,
BOUND-003/OD-01). Owns `payments`/`invoices`; calls into `membership.service` for
any `subscriptions` write, per Architecture §4.4's module-boundary rule (billing
never writes `subscriptions` directly).

TEST/SANDBOX SCOPE ONLY — restated per explicit instruction, not just implied:
no production Razorpay credentials exist in this environment, `CORE_BILLING_ENABLED`
defaults False (core/config.py) and is checked first in `initiate_checkout`, and
nothing in this file or `integrations/payment_service.py` ever sets that flag —
only `PATCH /admin/settings/billing-flags` (API Spec §10.9, not yet implemented)
would, and per BOUND-003 that's a manual, deliberate, legal-sign-off-gated action.

WRITTEN, NOT EXECUTED — no real database, Redis, or Razorpay endpoint has been
reached in this session. Every "verified" claim about this file lives in
work_memory.md, stated precisely (import/routing-level only, not runtime).
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.config import get_settings
from app.core.errors import QFinanceAPIError
from app.integrations import invoice_service, payment_service
from app.modules.analytics.models import emit_event
from app.modules.billing import pending_checkout_store
from app.modules.billing.models import Invoice, Payment
from app.modules.membership import service as membership_service

settings = get_settings()


async def initiate_checkout(db: AsyncSession, *, user_id: uuid.UUID, plan_code: str = "CORE") -> dict:
    """API Spec §3.2.1. BOUND-003 gate is the very first thing checked — every other
    line below is unreachable while `CORE_BILLING_ENABLED` is False, which it is by
    default and remains so until OD-01 legal sign-off, per Architecture/PRD."""
    if not settings.CORE_BILLING_ENABLED:
        raise QFinanceAPIError(
            "BILLING_NOT_YET_AVAILABLE",
            "Paid membership is not yet available. Please check back soon.",
            503,
        )

    plan = await membership_service.get_plan_by_code(db, plan_code)
    order = payment_service.create_order(
        amount_paise=plan.price_paise, currency=plan.currency, receipt=str(uuid.uuid4())
    )
    await pending_checkout_store.create_pending_checkout(
        order_id=order["id"], user_id=user_id, plan_code=plan.code, amount_paise=plan.price_paise
    )
    return {
        "razorpay_order_id": order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "amount_paise": plan.price_paise,
    }


async def _get_any_subscription_for_user(db: AsyncSession, user_id: uuid.UUID):
    result = await db.execute(
        select(membership_service.Subscription)
        .where(membership_service.Subscription.user_id == user_id)
        .order_by(membership_service.Subscription.created_at.desc())
    )
    return result.scalars().first()


async def _handle_payment_captured(db: AsyncSession, entity: dict) -> dict:
    gateway_reference_id = entity["id"]
    order_id = entity.get("order_id")
    amount_paise = entity["amount"]

    # Idempotency (ERR-003) — checked explicitly before insert, not relied on the DB
    # UNIQUE constraint alone, so a replayed webhook gets a clean 200 no-op response
    # rather than surfacing a raw integrity-error path to the caller.
    existing = await db.execute(select(Payment).where(Payment.gateway_reference_id == gateway_reference_id))
    if existing.scalar_one_or_none() is not None:
        return {"status": "already_processed"}

    pending = await pending_checkout_store.get_pending_checkout(order_id) if order_id else None
    if pending is None:
        # No pending-checkout record — either the TTL expired or this webhook doesn't
        # correspond to a checkout this system initiated. Write nothing rather than
        # guess which user/plan this belongs to.
        raise QFinanceAPIError(
            "PENDING_CHECKOUT_NOT_FOUND",
            "No matching pending checkout for this payment.",
            400,
        )

    now = datetime.now(timezone.utc)
    period_end = now + timedelta(days=30)  # billing_interval='monthly' for both current plans

    subscription = await membership_service.activate_subscription(
        db,
        user_id=pending["user_id"],
        plan_code=pending["plan_code"],
        current_period_start=now,
        current_period_end=period_end,
    )

    payment = Payment(
        id=uuid.uuid4(),
        subscription_id=subscription.id,
        amount_paise=amount_paise,
        currency="INR",
        status="succeeded",
        gateway_reference_id=gateway_reference_id,
        billing_period_start=now,
        billing_period_end=period_end,
    )
    db.add(payment)
    await db.flush()

    invoice_fields = invoice_service.build_invoice_fields(
        amount_paise=amount_paise,
        billing_period=now.strftime("%Y-%m"),
        gateway_reference=gateway_reference_id,
    )
    invoice = Invoice(
        id=uuid.uuid4(),
        user_id=pending["user_id"],
        payment_id=payment.id,
        currency="INR",
        payment_status="succeeded",
        invoice_date=date.today(),
        **invoice_fields,
    )
    db.add(invoice)

    await emit_event(
        db, user_id=pending["user_id"], event_type="payment_completed",
        entity_type="subscription", entity_id=subscription.id,
        metadata={"amount_paise": amount_paise, "gateway_reference_id": gateway_reference_id},
    )

    await pending_checkout_store.clear_pending_checkout(order_id)
    await db.commit()
    return {"status": "processed"}


async def _handle_payment_failed(db: AsyncSession, entity: dict) -> dict:
    """PAY-003 — failure never silently grants access; no subscription/invoice change
    beyond the OD-06 grace-period state transition itself, per API Spec §3.2.2's
    explicit wording.

    RENEWAL failure (an existing subscription already `active`): transitions it to
    `past_due` and starts the 7-day grace period via `membership_service.mark_past_due`
    (OD-06) — this was a real, separate gap fixed this pass: without it, nothing ever
    moved a subscription into `past_due`, so `expire_overdue_subscriptions` (the daily
    downgrade job) would never have found anything to act on and OD-06's grace period
    would never actually run.

    GENUINE, FLAGGED SPEC/SCHEMA GAP (not silently resolved — see work_memory.md):
    `payments.subscription_id` is `NOT NULL` (Database Schema §5), but a user's very
    first payment attempt, if it fails, has no `subscriptions` row yet to reference —
    none is created on failure (per this endpoint's own spec), and none exists from
    before (this is their first attempt). For a RENEWAL failure (the user already has
    a subscription row from a prior period), `subscription_id` can validly reference
    that existing row and this function does so. For a first-ever-payment failure,
    there is no schema-compliant way to insert the `payments` row at all without
    either violating the NOT NULL constraint or violating "no subscription change" —
    this is recorded via `audit_logs` only in that case, and the gap is surfaced here
    rather than worked around by (a) creating a placeholder subscription row (would
    contradict §3.2.1's own "subscriptions means confirmed billing history only"
    resolution) or (b) altering the schema (explicitly out of scope — "do not
    redesign the database"). This needs a founder decision, not an autonomous fix.
    """
    gateway_reference_id = entity["id"]
    order_id = entity.get("order_id")

    existing = await db.execute(select(Payment).where(Payment.gateway_reference_id == gateway_reference_id))
    if existing.scalar_one_or_none() is not None:
        return {"status": "already_processed"}

    pending = await pending_checkout_store.get_pending_checkout(order_id) if order_id else None
    user_id = pending["user_id"] if pending else None

    existing_subscription = await _get_any_subscription_for_user(db, user_id) if user_id else None

    if existing_subscription is None:
        # The flagged gap case — record via audit_logs only, write no `payments` row.
        await write_audit_log(
            db, actor_id=user_id, action_type="payment.failed_no_subscription_row",
            target_entity_type="payment", target_entity_id=uuid.uuid4(),
            after_state={"gateway_reference_id": gateway_reference_id, "raw_entity": entity},
            reason=(
                "First-payment failure with no existing subscription row — "
                "payments.subscription_id NOT NULL cannot be satisfied without "
                "either a schema change or contradicting BOUND/spec rules. "
                "See billing/service.py:_handle_payment_failed docstring."
            ),
        )
        await db.commit()
        return {"status": "logged_only_schema_gap"}

    payment = Payment(
        id=uuid.uuid4(),
        subscription_id=existing_subscription.id,
        amount_paise=entity["amount"],
        currency="INR",
        status="failed",
        gateway_reference_id=gateway_reference_id,
        billing_period_start=existing_subscription.current_period_start,
        billing_period_end=existing_subscription.current_period_end,
    )
    db.add(payment)

    # OD-06 grace period — only start it if this subscription isn't already in the
    # grace period (a second failed retry during an existing grace window shouldn't
    # reset the 7-day clock; mark_past_due would otherwise silently extend it).
    if existing_subscription.status == "active":
        await membership_service.mark_past_due(db, subscription_id=existing_subscription.id)

    await db.commit()
    return {"status": "processed"}


async def handle_webhook(db: AsyncSession, *, raw_body: bytes, signature: str) -> dict:
    """API Spec §3.2.2. Signature verification happens BEFORE any DB write is
    attempted, and before the body is even parsed as JSON for routing purposes."""
    if not payment_service.verify_webhook_signature(raw_body=raw_body, signature=signature):
        raise QFinanceAPIError("INVALID_WEBHOOK_SIGNATURE", "Webhook signature verification failed.", 400)

    body = json.loads(raw_body)
    event = body.get("event")

    if event == "payment.captured":
        entity = body["payload"]["payment"]["entity"]
        return await _handle_payment_captured(db, entity)
    if event == "payment.failed":
        entity = body["payload"]["payment"]["entity"]
        return await _handle_payment_failed(db, entity)

    # Any other event type is acknowledged but ignored — Razorpay expects a 200 for
    # events it sends that this integration doesn't act on, per standard webhook
    # practice; nothing is written.
    return {"status": "ignored", "event": event}


async def list_invoices(db: AsyncSession, *, user_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Invoice], int]:
    """API Spec §3.4.1."""
    from sqlalchemy import func

    stmt = (
        select(Invoice)
        .where(Invoice.user_id == user_id)
        .order_by(Invoice.invoice_date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    count_stmt = select(func.count()).select_from(Invoice).where(Invoice.user_id == user_id)
    total = (await db.execute(count_stmt)).scalar_one()
    items = (await db.execute(stmt)).scalars().all()
    return list(items), total
