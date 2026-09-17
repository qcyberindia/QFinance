"""EmailService — Architecture §4.4 provider abstraction (Resend, per OD-11/config's
`RESEND_API_KEY`). No route or service.py outside this file may call an email
provider's API directly.

DELIBERATELY DIFFERENT FAILURE BEHAVIOR FROM `payment_service.py`, and this
difference is intentional, not an inconsistency: `PaymentService` is allowed to fail
loudly because every caller of it sits behind `CORE_BILLING_ENABLED` (default False)
— nothing reaches it in a normal dev/test environment, so a hard failure there is
safe and even desirable (surfaces a real misconfiguration immediately). Email
verification is NOT optional/flag-gated the same way — `POST /auth/register` always
runs, in every environment, including this one, which has no real `RESEND_API_KEY`
configured. If this module raised on missing credentials the way `payment_service.py`
does, registration itself would break in any environment without real Resend
credentials, which is not what a "dev-safe adapter" should do.

So: with no `RESEND_API_KEY` configured, every `send_*` function here returns
normally (does not raise, does not block the caller) but does NOT claim a real email
was sent — it returns `{"sent": False, "reason": "no_provider_configured"}` and logs
(at INFO level, never including the raw token/link) that a send was skipped. With a
real key configured, it calls Resend's REST API for real (via `httpx`, not a
dedicated SDK — Resend's API is a simple REST POST, not worth a guarded-lazy-import
SDK dependency the way Razorpay's Python SDK was) and returns
`{"sent": True, "resend_id": ...}` on success, or raises `EmailServiceError` on a
genuine provider failure (network error, 4xx/5xx from Resend) — callers (auth/service.py)
catch this and log it, but do NOT let it fail the registration/reset-request
transaction itself; see auth/service.py's own comments for that boundary.

CRITICAL: never logs the raw verification/reset token or the full link containing it
— only that a send was attempted/skipped/succeeded, and the recipient's email address
(which is not a secret in this context — it's the account's own identifier).

WRITTEN, NOT EXECUTED — no real Resend API call has been made in this session; no
`RESEND_API_KEY` is configured in this environment.
"""
import logging

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger("qfinance.email_service")

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "Qfinera <noreply@qfinance.example>"  # placeholder domain — not a real sending domain (domain string itself intentionally left unchanged per explicit instruction: do not invent a production sending domain)


class EmailServiceError(Exception):
    """Raised only for a genuine provider-side failure when real credentials ARE
    configured (network error, non-2xx from Resend). Never raised merely because
    credentials are absent — that path returns {"sent": False, ...} instead."""


def _send_via_resend(*, to_email: str, subject: str, html_body: str) -> dict:
    # BUG FIX (this audit pass): the original code imported httpx unguarded here.
    # httpx is currently listed only under this project's `dev` optional-dependency
    # group in pyproject.toml, NOT the base `[project.dependencies]` list (a real,
    # separate gap — flagged in the final report, not fixed here since "Python
    # packaging cleanup" is explicitly out of scope for this task). Until that's
    # corrected, a production install without the dev extras would hit this import
    # the moment a real RESEND_API_KEY is configured and someone actually registers,
    # raising a raw ModuleNotFoundError instead of this module's own clean
    # EmailServiceError — inconsistent with payment_service.py's established
    # lazy-import-with-ImportError-guard pattern for the razorpay SDK. Matched here.
    try:
        import httpx
    except ImportError as e:
        raise EmailServiceError("The 'httpx' package is not installed.") from e

    try:
        response = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={"from": FROM_ADDRESS, "to": [to_email], "subject": subject, "html": html_body},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as e:
        raise EmailServiceError(f"Resend send failed: {e}") from e
    return {"sent": True, "resend_id": response.json().get("id")}


def _send_or_skip(*, to_email: str, subject: str, html_body: str, log_label: str) -> dict:
    if not settings.RESEND_API_KEY:
        logger.info("EmailService: skipping send (%s) to %s — no RESEND_API_KEY configured.", log_label, to_email)
        return {"sent": False, "reason": "no_provider_configured"}
    result = _send_via_resend(to_email=to_email, subject=subject, html_body=html_body)
    logger.info("EmailService: sent (%s) to %s via Resend (id=%s).", log_label, to_email, result.get("resend_id"))
    return result


def send_verification_email(*, to_email: str, verification_link: str) -> dict:
    """AUTH-001/002. `verification_link` is expected to already be the full
    frontend URL with the token embedded (e.g. https://.../verify-email?token=...)
    — this function does not construct that URL itself, since the frontend's route
    shape isn't this module's concern (Architecture §4.4 boundary)."""
    return _send_or_skip(
        to_email=to_email,
        subject="Verify your Qfinera email address",
        html_body=f'<p>Confirm your email to finish setting up your Qfinera account.</p>'
                  f'<p><a href="{verification_link}">Verify email address</a></p>'
                  f'<p>This link expires in 24 hours. If you did not create a Qfinera account, ignore this email.</p>',
        log_label="verification",
    )


def send_password_reset_email(*, to_email: str, reset_link: str) -> dict:
    """AUTH-005."""
    return _send_or_skip(
        to_email=to_email,
        subject="Reset your Qfinera password",
        html_body=f'<p>A password reset was requested for your Qfinera account.</p>'
                  f'<p><a href="{reset_link}">Reset your password</a></p>'
                  f'<p>This link expires in 1 hour and can only be used once. '
                  f'If you did not request this, you can safely ignore this email — your password will not change.</p>',
        log_label="password_reset",
    )
