"""Integration tests for membership + billing — checkout gating, webhook
idempotency/signature verification, subscription lifecycle (activate/cancel/
grace-period/expire), entitlement sync, and invoice listing.

STATUS: WRITTEN. NOT EXECUTABLE IN CURRENT ENVIRONMENT — requires real
PostgreSQL + Redis, neither reachable from this session (see work_memory.md).
The one piece of this module's logic that IS genuinely unit-tested is in
test_membership_entitlement.py (the pure role-grant/revoke helpers) — everything
below is written but unverified beyond manual review against API Spec §3.
"""
import pytest


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_plans_endpoint_returns_exactly_free_and_core(client):
    resp = await client.get("/api/v1/membership/plans")
    assert resp.status_code == 200
    codes = {p["code"] for p in resp.json()}
    assert codes == {"FREE", "CORE"}
    core = next(p for p in resp.json() if p["code"] == "CORE")
    assert core["price_paise"] == 79900  # OD-22


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_membership_me_defaults_to_free_with_no_subscription_row(client, free_member):
    resp = await client.get("/api/v1/membership/me", headers=free_member.auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_code"] == "FREE"
    assert body["status"] == "active"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_checkout_returns_503_when_billing_disabled(client, free_member, monkeypatch):
    """BOUND-003 — CORE_BILLING_ENABLED defaults False; this must be the very
    first thing checked, before any Razorpay call is attempted."""
    resp = await client.post("/api/v1/membership/checkout", headers=free_member.csrf_headers)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "BILLING_NOT_YET_AVAILABLE"


@pytest.mark.skip(reason="requires a real PostgreSQL test database and a mocked Razorpay client")
async def test_checkout_requires_verified_email(client, unverified_member):
    resp = await client.post("/api/v1/membership/checkout", headers=unverified_member.csrf_headers)
    assert resp.status_code == 403


@pytest.mark.skip(reason="requires a real PostgreSQL test database, Redis, and a mocked Razorpay client")
async def test_webhook_rejects_invalid_signature_and_writes_nothing(client, db_session):
    resp = await client.post(
        "/api/v1/webhooks/razorpay",
        content=b'{"event": "payment.captured", "payload": {}}',
        headers={"X-Razorpay-Signature": "not-a-real-signature"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_WEBHOOK_SIGNATURE"
    # Assert no `payments` row was inserted.


@pytest.mark.skip(reason="requires a real PostgreSQL test database, Redis, and a mocked Razorpay client")
async def test_webhook_payment_captured_activates_subscription_and_grants_member(
    client, free_member, db_session, valid_razorpay_signature,
):
    """The core entitlement-sync regression test for the bug fixed this session:
    after a successful `payment.captured` webhook, the user's `profiles.role_grants`
    must include MEMBER, not just their `subscriptions` row being active — a
    `require_role("MEMBER")`-gated endpoint (e.g. `POST /research`) must now
    succeed for this user where it previously would have failed."""
    # ... initiate checkout, obtain pending order_id, fire webhook with matching
    # order_id and a valid signature ...
    resp = await client.post(
        "/api/v1/webhooks/razorpay",
        content=b"...",  # valid payment.captured payload referencing the pending order
        headers={"X-Razorpay-Signature": valid_razorpay_signature},
    )
    assert resp.status_code == 200

    membership_resp = await client.get("/api/v1/membership/me", headers=free_member.auth_headers)
    assert membership_resp.json()["plan_code"] == "CORE"
    assert membership_resp.json()["status"] == "active"

    # The actual entitlement check: a MEMBER-gated endpoint now succeeds.
    research_resp = await client.post("/api/v1/research", json={
        "company_id": "00000000-0000-0000-0000-000000000001", "research_type": "deep_dive",
    }, headers=free_member.csrf_headers)
    assert research_resp.status_code == 201


@pytest.mark.skip(reason="requires a real PostgreSQL test database, Redis, and a mocked Razorpay client")
async def test_webhook_is_idempotent_on_replay(client, db_session, valid_razorpay_signature):
    """ERR-003 — the same gateway_reference_id delivered twice must not create
    two `payments`/`invoices` rows or double-activate anything."""
    payload = b"..."  # same payment.captured payload both times
    r1 = await client.post("/api/v1/webhooks/razorpay", content=payload,
                            headers={"X-Razorpay-Signature": valid_razorpay_signature})
    r2 = await client.post("/api/v1/webhooks/razorpay", content=payload,
                            headers={"X-Razorpay-Signature": valid_razorpay_signature})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_processed"
    # Assert exactly one `payments` row exists for that gateway_reference_id.


@pytest.mark.skip(reason="requires a real PostgreSQL test database, Redis, and a mocked Razorpay client")
async def test_webhook_payment_failed_on_renewal_starts_grace_period(
    client, core_member_with_active_subscription, db_session, valid_razorpay_signature,
):
    """OD-06 regression test for the second bug fixed this session: a renewal
    failure must transition the existing subscription to `past_due` with
    `grace_period_ends_at` ~7 days out, and MEMBER access must be retained
    through the grace period (not revoked immediately)."""
    resp = await client.post(
        "/api/v1/webhooks/razorpay",
        content=b"...",  # payment.failed payload for a renewal of an existing subscription
        headers={"X-Razorpay-Signature": valid_razorpay_signature},
    )
    assert resp.status_code == 200
    membership_resp = await client.get(
        "/api/v1/membership/me", headers=core_member_with_active_subscription.auth_headers,
    )
    assert membership_resp.json()["status"] == "past_due"
    assert membership_resp.json()["grace_period_ends_at"] is not None
    # Assert MEMBER is still in profiles.role_grants — access retained during grace.


@pytest.mark.skip(reason="requires a real PostgreSQL test database")
async def test_grace_period_expiry_job_downgrades_and_revokes_member(db_session, past_due_subscription_expired):
    from app.modules.membership.service import expire_overdue_subscriptions
    count = await expire_overdue_subscriptions(db_session)
    assert count == 1
    # Assert subscription.status == 'expired' and MEMBER removed from role_grants.


@pytest.mark.skip(reason="requires a real PostgreSQL test database")
async def test_canceled_subscription_past_period_end_is_downgraded_by_the_same_job(
    db_session, canceled_subscription_past_period_end,
):
    """MEM-007 — access continues through the paid period after cancellation, but
    the same grace-period job must eventually downgrade it once the period truly
    ends (this was the second half of the grace-period-job bug fixed this session
    — it previously only looked at `past_due`, never `canceled`)."""
    from app.modules.membership.service import expire_overdue_subscriptions
    count = await expire_overdue_subscriptions(db_session)
    assert count == 1


@pytest.mark.skip(reason="requires a real PostgreSQL test database")
async def test_cancel_does_not_immediately_revoke_member_access(client, core_member_with_active_subscription):
    resp = await client.post("/api/v1/membership/cancel", headers=core_member_with_active_subscription.csrf_headers)
    assert resp.status_code == 200
    assert resp.json()["canceled"] is True
    # Assert MEMBER is still in role_grants immediately after cancel — access
    # continues to current_period_end, per MEM-007.


@pytest.mark.skip(reason="requires a real PostgreSQL test database")
async def test_invoices_endpoint_is_self_scoped(client, member_a, member_b, member_a_invoice):
    resp = await client.get("/api/v1/membership/invoices", headers=member_b.auth_headers)
    ids = [i["gateway_reference"] for i in resp.json()["items"]] if "gateway_reference" in str(resp.json()) else []
    # Assert member_a's invoice never appears in member_b's list.
