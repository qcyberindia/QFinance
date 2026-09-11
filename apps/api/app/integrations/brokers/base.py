"""BrokerAdapter protocol — Architecture V2 §3.

`portfolio/service.py` calls only this protocol, never `zerodha.py` (or any
future broker adapter) directly by name for business logic — mirrors the
existing `PaymentService`/`EmailService` abstraction already established for
Razorpay/Resend (`app/integrations/payment_service.py`,
`app/integrations/email_service.py`). Adding a second broker later means
adding a second adapter module implementing this same protocol, not touching
`portfolio/service.py`.

READ-ONLY BY DESIGN: this protocol has no method that could place an order,
modify an account, or issue any instruction to the broker — only `connect`
(exchange a login callback for a stored session) and two read methods. This
is a structural constraint, not just a policy: there is no method here for a
caller to misuse into a write/trade action even if someone tried.

WRITTEN, NOT EXECUTED.
"""
from typing import Any, Protocol


class BrokerConnectionError(Exception):
    """Raised for a genuine broker-side failure: invalid/expired
    authorization, a Kite API error, a network failure, etc. Never raised
    merely because credentials are unconfigured — see
    `BrokerNotConfiguredError` for that case, mirroring EmailService's
    equivalent split between "not configured" (safe, non-fatal) and "genuine
    provider failure" (raised)."""


class BrokerNotConfiguredError(Exception):
    """Raised when ZERODHA_API_KEY/ZERODHA_API_SECRET are unset. Callers
    (portfolio/service.py) convert this into the PF.1-documented
    `BROKER_NOT_CONFIGURED` 503 API error — the application itself must
    still start normally with no credentials configured (a dev/test
    requirement, Architecture V2 §3)."""


class BrokerAdapter(Protocol):
    """Every method is read-only or connection-lifecycle only. No method
    exists here for placing orders, modifying holdings, or any
    account-management action — BOUND-001 is enforced structurally by what
    this interface does NOT expose, not only by convention."""

    def get_login_url(self) -> str:
        """PF.1 — returns the broker's own login/authorization redirect URL.
        Raises BrokerNotConfiguredError if credentials are unset."""
        ...

    def exchange_request_token(self, *, request_token: str) -> dict[str, Any]:
        """PF.2 — exchanges the callback's request_token for a session/access
        token. Returns a dict with at least {"access_token": str,
        "broker_user_id": str | None} — never logged, never returned to the
        client as-is (portfolio/service.py stores only what
        broker_connections needs and returns only connection *status* to the
        API caller, never the token itself). Raises BrokerConnectionError on
        a genuine exchange failure (invalid/expired request_token, etc.)."""
        ...

    def fetch_holdings(self, *, access_token: str) -> list[dict[str, Any]]:
        """PF.4. Raises BrokerConnectionError on an expired/invalid token or
        any other broker-API failure — callers distinguish an expired-token
        failure (prompt reconnect) from other failures only by inspecting
        the broker's own error semantics where practical; MVP treats any
        BrokerConnectionError here uniformly as BROKER_AUTH_FAILED, per the
        locked error-code list (API Spec V2 §9) not distinguishing further."""
        ...

    def fetch_positions(self, *, access_token: str) -> list[dict[str, Any]]:
        """PF.4 — 'positions where supported by the Kite API' (PRD V2 §4.1).
        Returns an empty list rather than raising if the broker genuinely has
        no positions endpoint result for this account (e.g. no open F&O
        positions) — an empty list is a normal, valid state, not an error."""
        ...
