"""Real, DB/Redis-free tests for EmailService's dev-safe behavior — the one part of
this pass genuinely testable with zero external dependencies, since no
RESEND_API_KEY is configured in this environment (by design, matching the
PaymentService/billing precedent).

STATUS: WRITTEN, NOT EXECUTED IN THIS SESSION — no `pytest` has been run against the
real repository in this turn. Run with:
    cd /home/prd/Projects/QFinance/apps/api && PYTHONPATH=. pytest -q tests/test_email_service_pure_logic.py
"""
from app.integrations.email_service import send_password_reset_email, send_verification_email


def test_send_verification_email_does_not_raise_without_credentials():
    """No RESEND_API_KEY configured — must return a clear 'skipped' result, never
    raise, and never block whatever called it (registration)."""
    result = send_verification_email(to_email="test@example.com", verification_link="http://x/verify?token=abc")
    assert result == {"sent": False, "reason": "no_provider_configured"}


def test_send_password_reset_email_does_not_raise_without_credentials():
    result = send_password_reset_email(to_email="test@example.com", reset_link="http://x/reset?token=abc")
    assert result == {"sent": False, "reason": "no_provider_configured"}
