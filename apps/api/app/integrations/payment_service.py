"""PaymentService — Architecture §4.4 provider abstraction. No route or service.py
outside this file may import the `razorpay` SDK directly (API Spec §13's explicit
verification point: "every external provider is called only through its Architecture
§4.4 abstraction").

CRITICAL SCOPE BOUNDARY (per explicit instruction — restated here, not just implied):
- This is the TEST/SANDBOX payment architecture only.
- No production Razorpay credentials are read, referenced, or assumed anywhere below.
- `settings.RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`/`RAZORPAY_WEBHOOK_SECRET` are all
  `None` by default (core/config.py) and remain unset in this environment — there is
  no real Razorpay account behind this code, sandbox or otherwise, in this session.
- `CORE_BILLING_ENABLED` (core/config.py) defaults `False` and gates every caller of
  this module (billing/service.py checks it before calling `create_order`) — per
  BOUND-003, this must not flip `True` in production before OD-01 legal sign-off, and
  nothing in this file flips it; it is only ever read.
- This module has NOT been executed against a real Razorpay sandbox or production
  endpoint in this session — no network call has been attempted. It is structurally
  correct against the real `razorpay` Python SDK's documented interface, not verified
  by execution.

WRITTEN, NOT EXECUTED.
"""
import hashlib
import hmac
from typing import Any

from app.core.config import get_settings

settings = get_settings()


class PaymentServiceError(Exception):
    """Raised when the underlying gateway call fails or credentials are absent."""


def _get_client():
    """Lazily imports and constructs the Razorpay client only when actually called —
    keeps this module importable (and the rest of the app's import graph verifiable,
    per this project's established C.4-style check) even when the `razorpay` package
    isn't installed or credentials aren't configured, which is the case in this
    environment right now."""
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentServiceError(
            "Razorpay credentials are not configured. This is expected in this "
            "environment (test/sandbox keys have not been provisioned) — "
            "CORE_BILLING_ENABLED should be False, which prevents this path from "
            "being reached via the API in the first place (see billing/service.py)."
        )
    try:
        import razorpay
    except ImportError as e:
        raise PaymentServiceError(
            "The 'razorpay' package is not installed in this environment. "
            "Added to pyproject.toml dependencies but not installed/verified this session."
        ) from e
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order(*, amount_paise: int, currency: str, receipt: str) -> dict[str, Any]:
    """Creates a Razorpay Order (the pre-payment object the frontend's checkout widget
    needs). Does NOT create a `subscriptions` row — API Spec §3.2.1's explicit
    resolution of Architecture §17 Remaining Technical Question #5: the pending
    pre-payment state is held in Redis by billing.service, not the DB, until the
    webhook confirms payment."""
    client = _get_client()
    order = client.order.create(
        {"amount": amount_paise, "currency": currency, "receipt": receipt, "payment_capture": 1}
    )
    return order


def verify_webhook_signature(*, raw_body: bytes, signature: str) -> bool:
    """API Spec §3.2.2 — verifies BEFORE any DB write is attempted. Uses HMAC-SHA256
    over the raw request body with `RAZORPAY_WEBHOOK_SECRET`, per Razorpay's documented
    webhook-signature scheme — implemented directly (not via the SDK helper) so this
    function has zero dependency on the `razorpay` package being installed, since
    signature verification must be reachable even in test contexts that mock the SDK
    client out entirely."""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise PaymentServiceError(
            "RAZORPAY_WEBHOOK_SECRET is not configured — cannot verify a webhook "
            "signature. Expected in this environment; no webhook signature has "
            "actually been verified in this session."
        )
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
