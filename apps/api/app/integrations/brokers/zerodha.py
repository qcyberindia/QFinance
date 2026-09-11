"""ZerodhaAdapter — the only `BrokerAdapter` implementation in this MVP
(Architecture V2 §3). Wraps the Kite Connect API via the `kiteconnect` SDK.

CRITICAL SECURITY BOUNDARY, restated here (not just implied): no function in
this file ever logs `access_token`, `api_secret`, or `request_token`. Log
lines below reference only the operation name and, where relevant, the
broker's own opaque `kite_user_id` (not a secret — it's Zerodha's own account
identifier, already known to the member themselves).

Lazy SDK import, matching the established pattern in
`payment_service.py`/`email_service.py` — this module must remain importable
even if `kiteconnect` isn't installed, so the application can still start
(Architecture V2 §3: "the application itself must still start normally with
no credentials configured").

WRITTEN, NOT EXECUTED — no real Kite Connect API call has been made in this
session; no `ZERODHA_API_KEY`/`ZERODHA_API_SECRET` is configured in this
environment.
"""
import logging
from typing import Any

from app.core.config import get_settings
from app.integrations.brokers.base import BrokerConnectionError, BrokerNotConfiguredError

settings = get_settings()
logger = logging.getLogger("qfinance.broker.zerodha")


def _require_configured() -> None:
    if not settings.ZERODHA_API_KEY or not settings.ZERODHA_API_SECRET:
        raise BrokerNotConfiguredError("ZERODHA_API_KEY/ZERODHA_API_SECRET are not configured.")


def _get_kite_client(*, access_token: str | None = None):
    """Lazy import + client construction, mirroring `payment_service.py`'s
    `_get_client()`. Raises `BrokerConnectionError` (not a raw
    `ModuleNotFoundError`) if the `kiteconnect` package isn't installed —
    matching the exact fix applied to `email_service.py`'s equivalent
    unguarded-import gap earlier this project, applied correctly here from
    the start rather than needing a later audit fix."""
    _require_configured()
    try:
        from kiteconnect import KiteConnect
    except ImportError as e:
        raise BrokerConnectionError("The 'kiteconnect' package is not installed.") from e
    kite = KiteConnect(api_key=settings.ZERODHA_API_KEY)
    if access_token:
        kite.set_access_token(access_token)
    return kite


class ZerodhaAdapter:
    """Implements the `BrokerAdapter` protocol (see base.py) — no method here
    places an order, modifies a position, or does anything beyond
    connect/read. Not a subclass of a Protocol (Python Protocols use
    structural typing) — `portfolio/service.py` type-hints against
    `BrokerAdapter` and this class satisfies it by shape."""

    def get_login_url(self) -> str:
        _require_configured()
        kite = _get_kite_client()
        return kite.login_url()

    def exchange_request_token(self, *, request_token: str) -> dict[str, Any]:
        _require_configured()
        kite = _get_kite_client()
        try:
            session_data = kite.generate_session(request_token, api_secret=settings.ZERODHA_API_SECRET)
        except Exception as e:  # noqa: BLE001 — the kiteconnect SDK's own exception
            # hierarchy varies by version and isn't guaranteed importable if the
            # package itself is absent; converting any failure here uniformly to
            # BrokerConnectionError keeps this adapter's public contract stable.
            logger.warning("Zerodha request_token exchange failed: %s", type(e).__name__)
            raise BrokerConnectionError("Failed to exchange request_token for a Zerodha session.") from e
        logger.info("Zerodha session established for kite_user_id=%s", session_data.get("user_id"))
        return {
            "access_token": session_data["access_token"],
            "broker_user_id": session_data.get("user_id"),
        }

    def fetch_holdings(self, *, access_token: str) -> list[dict[str, Any]]:
        _require_configured()
        kite = _get_kite_client(access_token=access_token)
        try:
            return kite.holdings()
        except Exception as e:  # noqa: BLE001 — see exchange_request_token's comment
            logger.warning("Zerodha holdings fetch failed: %s", type(e).__name__)
            raise BrokerConnectionError("Failed to fetch holdings from Zerodha.") from e

    def fetch_positions(self, *, access_token: str) -> list[dict[str, Any]]:
        _require_configured()
        kite = _get_kite_client(access_token=access_token)
        try:
            positions = kite.positions()
        except Exception as e:  # noqa: BLE001
            logger.warning("Zerodha positions fetch failed: %s", type(e).__name__)
            raise BrokerConnectionError("Failed to fetch positions from Zerodha.") from e
        # Kite's positions() returns {"net": [...], "day": [...]} — "net" is
        # the member's actual current position set; "day" is intraday-only
        # and not meaningful for a buy-and-hold investor workspace like this
        # one, so it's intentionally not surfaced here (PRD V2 §4.1: "positions
        # where the Kite API supports it" — net positions is the supported,
        # relevant subset for this product).
        return positions.get("net", []) if isinstance(positions, dict) else []
