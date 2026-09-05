"""Real, executable tests for the parts of billing that need NO database, Redis, or
Razorpay connection — the BOUND-003/OD-01 gate and PaymentService's credential-absence
guards. These are exactly the parts of billing/service.py and
integrations/payment_service.py that are safe and meaningful to test in this
environment right now, since production credentials genuinely don't exist here.

STATUS: see work_memory.md for exactly what was executed and where (same C.4-style
discipline as test_research_validation.py) — this docstring does not itself claim
execution; the work_memory.md entry is the source of truth for that claim.
"""
import uuid

import pytest

from app.core.errors import QFinanceAPIError
from app.integrations.payment_service import PaymentServiceError, create_order, verify_webhook_signature
from app.modules.billing.service import initiate_checkout


@pytest.mark.asyncio
async def test_checkout_blocked_while_core_billing_disabled():
    """BOUND-003 — the single most important test in this file. CORE_BILLING_ENABLED
    defaults False (core/config.py); this must reject the request before touching the
    database at all (passing db=None and it must never be used)."""
    with pytest.raises(QFinanceAPIError) as exc_info:
        await initiate_checkout(db=None, user_id=uuid.uuid4())
    assert exc_info.value.code == "BILLING_NOT_YET_AVAILABLE"
    assert exc_info.value.status_code == 503


def test_create_order_raises_cleanly_without_credentials():
    """No RAZORPAY_KEY_ID/SECRET configured in this environment (by design) — must
    raise a clear PaymentServiceError, never a raw AttributeError/None-related crash."""
    with pytest.raises(PaymentServiceError):
        create_order(amount_paise=79900, currency="INR", receipt="test-receipt")


def test_verify_webhook_signature_raises_cleanly_without_secret():
    """No RAZORPAY_WEBHOOK_SECRET configured in this environment (by design)."""
    with pytest.raises(PaymentServiceError):
        verify_webhook_signature(raw_body=b'{"event": "payment.captured"}', signature="deadbeef")
