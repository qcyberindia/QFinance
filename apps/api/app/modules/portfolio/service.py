"""Portfolio business logic — API Specification V2 §7 (PF.1-PF.4).

Calls only the `BrokerAdapter` protocol (Architecture V2 §3), never
`ZerodhaAdapter` by name for business logic — the default adapter instance is
constructed here (the one place broker-selection happens), and every
function accepts an `adapter` override purely so tests can inject a fake
without touching a real Kite Connect API or needing real credentials
(explicit instruction: "Do NOT require real Zerodha credentials in the test
suite").

WRITTEN, NOT EXECUTED — no real database or Kite Connect API has been reached
in this session.
"""
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.crypto import DecryptionError, EncryptionNotConfiguredError, decrypt_broker_token, encrypt_broker_token
from app.core.errors import NotFound, QFinanceAPIError
from app.integrations.brokers.base import (
    BrokerAdapter, BrokerConnectionError, BrokerNotConfiguredError, BrokerSessionExpiredError,
)
from app.integrations.brokers.zerodha import ZerodhaAdapter
from app.modules.portfolio.models import BrokerConnection

_DEFAULT_ADAPTER = ZerodhaAdapter()


def _utcnow() -> datetime:
    """Naive UTC — broker_connections' timestamp columns are TIMESTAMP
    WITHOUT TIME ZONE, and asyncpg rejects tz-aware values for them (the
    same convention research/service.py uses for `published_at`)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _adapter_or_default(adapter: BrokerAdapter | None) -> BrokerAdapter:
    return adapter if adapter is not None else _DEFAULT_ADAPTER


async def get_connection(db: AsyncSession, *, user_id: uuid.UUID) -> BrokerConnection | None:
    result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == user_id, BrokerConnection.broker == "zerodha")
    )
    return result.scalar_one_or_none()


async def get_login_url(*, state: str, adapter: BrokerAdapter | None = None) -> str:
    """PF.1. Appends the OAuth `state` via Kite's `redirect_params` (Kite
    sends those params back on the redirect). `BrokerNotConfiguredError` is
    translated to the locked `BROKER_NOT_CONFIGURED` 503 error code here."""
    try:
        base = _adapter_or_default(adapter).get_login_url()
    except BrokerNotConfiguredError as e:
        raise QFinanceAPIError("BROKER_NOT_CONFIGURED", "Zerodha integration is not yet available.", 503) from e
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}redirect_params={quote(urlencode({'state': state}), safe='')}"


async def complete_connection(
    db: AsyncSession, *, user_id: uuid.UUID, request_token: str, adapter: BrokerAdapter | None = None,
) -> BrokerConnection:
    """PF.2. Exchanges the callback's request_token for a Kite access_token
    and upserts the single `(user_id, 'zerodha')` connection row (UNIQUE
    constraint) — a reconnect after a prior disconnect/error updates the
    existing row rather than violating the unique constraint with a second
    insert."""
    try:
        session_data = _adapter_or_default(adapter).exchange_request_token(request_token=request_token)
    except BrokerNotConfiguredError as e:
        raise QFinanceAPIError("BROKER_NOT_CONFIGURED", "Zerodha integration is not yet available.", 503) from e
    except BrokerConnectionError as e:
        raise QFinanceAPIError("BROKER_AUTH_FAILED", "Failed to connect your Zerodha account. Please try again.", 400) from e

    # Encrypted at rest with the dedicated broker key (app/core/crypto.py,
    # BROKER_TOKEN_ENCRYPTION_SECRET). If it isn't configured the connection
    # fails cleanly — the token is never stored in plaintext.
    try:
        encrypted_token = encrypt_broker_token(session_data["access_token"])
    except EncryptionNotConfiguredError as e:
        raise QFinanceAPIError("BROKER_NOT_CONFIGURED", "Zerodha integration is not yet available.", 503) from e

    connection = await get_connection(db, user_id=user_id)
    now = _utcnow()
    if connection is None:
        connection = BrokerConnection(
            id=uuid.uuid4(), user_id=user_id, broker="zerodha", status="connected",
            access_token=encrypted_token, kite_user_id=session_data.get("broker_user_id"),
            connected_at=now,
        )
        db.add(connection)
    else:
        connection.status = "connected"
        connection.access_token = encrypted_token
        connection.kite_user_id = session_data.get("broker_user_id")
        connection.connected_at = now

    await write_audit_log(
        db, actor_id=user_id, action_type="portfolio.broker_connected",
        target_entity_type="broker_connection", target_entity_id=connection.id,
        after_state={"broker": "zerodha", "status": "connected"},
        # Deliberately no access_token/kite_user_id in the audit payload — the
        # audit log is not a secrets store, and kite_user_id, while not itself
        # a credential, adds no value to an audit trail of "connection happened."
    )
    await db.commit()
    return connection


async def get_connection_status_or_404(db: AsyncSession, *, user_id: uuid.UUID) -> BrokerConnection:
    connection = await get_connection(db, user_id=user_id)
    if connection is None or connection.status != "connected":
        raise QFinanceAPIError("BROKER_NOT_CONNECTED", "No active Zerodha connection.", 404)
    return connection


async def disconnect(db: AsyncSession, *, user_id: uuid.UUID) -> BrokerConnection:
    """PF.3 — clears the stored token and marks disconnected. Does NOT
    delete the row (matches this project's established soft-state
    convention elsewhere, e.g. subscriptions' status transitions rather than
    row deletion) — a future reconnect (PF.2) updates this same row."""
    connection = await get_connection(db, user_id=user_id)
    if connection is None:
        raise NotFound("No Zerodha connection found.")
    connection.status = "disconnected"
    connection.access_token = None
    await write_audit_log(
        db, actor_id=user_id, action_type="portfolio.broker_disconnected",
        target_entity_type="broker_connection", target_entity_id=connection.id,
        after_state={"broker": "zerodha", "status": "disconnected"},
    )
    await db.commit()
    return connection


async def _mark_needs_reconnect(db: AsyncSession, connection: BrokerConnection) -> None:
    """Expired/unusable session: clear the token and flag the connection so
    the UI asks the member to reconnect instead of retrying forever."""
    connection.status = "error"
    connection.access_token = None
    await db.commit()


SESSION_EXPIRED_MESSAGE = "Your Zerodha session has expired. Reconnect to refresh your portfolio."


async def get_portfolio(db: AsyncSession, *, user_id: uuid.UUID, adapter: BrokerAdapter | None = None) -> dict:
    """PF.4 — live, on-demand fetch (no cache/background sync in MVP,
    Architecture V2 §3). Kite access tokens expire daily: an expired or
    undecryptable session marks the connection `error` and returns
    BROKER_SESSION_EXPIRED (reconnect); any other broker failure returns
    BROKER_AUTH_FAILED and leaves the connection in place so a retry can
    succeed."""
    connection = await get_connection_status_or_404(db, user_id=user_id)
    try:
        access_token, used_legacy_key = decrypt_broker_token(connection.access_token or "")
    except (DecryptionError, EncryptionNotConfiguredError):
        await _mark_needs_reconnect(db, connection)
        raise QFinanceAPIError("BROKER_SESSION_EXPIRED", SESSION_EXPIRED_MESSAGE, 409)
    if used_legacy_key:
        # Written before the broker/AI key split: re-encrypt under the broker
        # key now so later reads never need the legacy key.
        connection.access_token = encrypt_broker_token(access_token)
        await db.commit()

    effective_adapter = _adapter_or_default(adapter)
    try:
        raw_holdings = effective_adapter.fetch_holdings(access_token=access_token)
        raw_positions = effective_adapter.fetch_positions(access_token=access_token)
    except BrokerSessionExpiredError as e:
        await _mark_needs_reconnect(db, connection)
        raise QFinanceAPIError("BROKER_SESSION_EXPIRED", SESSION_EXPIRED_MESSAGE, 409) from e
    except BrokerConnectionError as e:
        raise QFinanceAPIError(
            "BROKER_AUTH_FAILED",
            "We couldn't reach Zerodha just now. Try refreshing in a moment.", 502,
        ) from e

    holdings = [h for h in (normalize_holding(r) for r in raw_holdings or []) if h is not None]
    positions = [p for p in (normalize_position(r) for r in raw_positions or []) if p is not None]

    connection.last_synced_at = _utcnow()
    await db.commit()

    return {
        "holdings": holdings, "positions": positions,
        "summary": build_summary(holdings),
        "last_synced_at": connection.last_synced_at,
        "read_only_notice": "Read-only — Qfinera cannot place trades.",
    }


# ---------------------------------------------------------------------------
# Normalization + summary — pure functions over the broker's own numbers.
# Nothing here estimates or invents a value: a metric that can't be computed
# from every holding's actual data is returned as None ("Not available").
# ---------------------------------------------------------------------------

def _num(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n == n and n not in (float("inf"), float("-inf")) else None  # rejects NaN/inf


def _positive(value) -> float | None:
    n = _num(value)
    return n if n is not None and n > 0 else None


def normalize_holding(raw: dict) -> dict | None:
    """Kite holding -> Qfinera holding. Kite names the symbol
    `tradingsymbol`; quantity held = settled `quantity` + `t1_quantity`
    (bought, awaiting T+1 settlement) — together what the member owns."""
    if not isinstance(raw, dict):
        return None
    symbol = raw.get("tradingsymbol") or raw.get("trading_symbol")
    if not symbol:
        return None
    quantity = (_num(raw.get("quantity")) or 0.0) + (_num(raw.get("t1_quantity")) or 0.0)
    if quantity <= 0:
        return None
    average_price = _positive(raw.get("average_price"))
    last_price = _positive(raw.get("last_price"))
    invested = round(average_price * quantity, 2) if average_price is not None else None
    current = round(last_price * quantity, 2) if last_price is not None else None
    pnl = round(current - invested, 2) if current is not None and invested is not None else None
    day_change = _num(raw.get("day_change"))
    return {
        "trading_symbol": str(symbol),
        "exchange": raw.get("exchange"),
        "isin": raw.get("isin"),
        "quantity": quantity,
        "t1_quantity": _num(raw.get("t1_quantity")) or 0.0,
        "average_price": average_price,
        "last_price": last_price,
        "close_price": _positive(raw.get("close_price")),
        "invested_value": invested,
        "current_value": current,
        "pnl": pnl,
        "pnl_percent": round(pnl / invested * 100, 2) if pnl is not None and invested else None,
        "day_change_value": round(day_change * quantity, 2) if day_change is not None else None,
        "day_change_percent": _num(raw.get("day_change_percentage")),
        "allocation_percent": None,  # filled in by build_summary
    }


def normalize_position(raw: dict) -> dict | None:
    """Kite net position -> Qfinera position. Closed positions (net
    quantity 0) are dropped — they aren't something the member currently
    holds. P&L is Kite's own figure for the position."""
    if not isinstance(raw, dict):
        return None
    symbol = raw.get("tradingsymbol") or raw.get("trading_symbol")
    quantity = _num(raw.get("quantity"))
    if not symbol or not quantity:
        return None
    return {
        "trading_symbol": str(symbol),
        "exchange": raw.get("exchange"),
        "product": raw.get("product"),
        "quantity": quantity,
        "average_price": _positive(raw.get("average_price")),
        "last_price": _positive(raw.get("last_price")),
        "pnl": _num(raw.get("pnl")),
    }


def build_summary(holdings: list[dict]) -> dict:
    """Portfolio-level figures. Totals are only reported when EVERY holding
    has the required input (a partial sum would understate the portfolio
    without saying so); allocation/concentration use current value."""
    count = len(holdings)

    def total(key: str) -> float | None:
        values = [h[key] for h in holdings]
        return round(sum(values), 2) if count and all(v is not None for v in values) else None

    invested = total("invested_value")
    current = total("current_value")
    pnl = round(current - invested, 2) if current is not None and invested is not None else None
    day_change = total("day_change_value")
    previous_value = current - day_change if current is not None and day_change is not None else None

    if current:
        for h in holdings:
            h["allocation_percent"] = round(h["current_value"] / current * 100, 2)
        shares = sorted((h["allocation_percent"] for h in holdings), reverse=True)
        top_holding = shares[0]
        top_five = round(sum(shares[:5]), 2)
    else:
        top_holding = top_five = None

    return {
        "holdings_count": count,
        "invested_value": invested,
        "current_value": current,
        "pnl": pnl,
        "pnl_percent": round(pnl / invested * 100, 2) if pnl is not None and invested else None,
        "day_change_value": day_change,
        "day_change_percent": round(day_change / previous_value * 100, 2) if previous_value else None,
        "top_holding_percent": top_holding,
        "top_five_percent": top_five,
    }
