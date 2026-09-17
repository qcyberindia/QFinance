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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import NotFound, QFinanceAPIError
from app.integrations.brokers.base import BrokerAdapter, BrokerConnectionError, BrokerNotConfiguredError
from app.integrations.brokers.zerodha import ZerodhaAdapter
from app.modules.portfolio.models import BrokerConnection

_DEFAULT_ADAPTER = ZerodhaAdapter()


def _adapter_or_default(adapter: BrokerAdapter | None) -> BrokerAdapter:
    return adapter if adapter is not None else _DEFAULT_ADAPTER


async def get_connection(db: AsyncSession, *, user_id: uuid.UUID) -> BrokerConnection | None:
    result = await db.execute(
        select(BrokerConnection).where(BrokerConnection.user_id == user_id, BrokerConnection.broker == "zerodha")
    )
    return result.scalar_one_or_none()


async def get_login_url(*, adapter: BrokerAdapter | None = None) -> str:
    """PF.1. `BrokerNotConfiguredError` is translated to the locked
    `BROKER_NOT_CONFIGURED` 503 error code here, at the service boundary —
    the router stays a thin passthrough, consistent with every other
    module's established error-handling pattern in this codebase."""
    try:
        return _adapter_or_default(adapter).get_login_url()
    except BrokerNotConfiguredError as e:
        raise QFinanceAPIError("BROKER_NOT_CONFIGURED", "Zerodha integration is not yet available.", 503) from e


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

    connection = await get_connection(db, user_id=user_id)
    now = datetime.now(timezone.utc)
    if connection is None:
        connection = BrokerConnection(
            id=uuid.uuid4(), user_id=user_id, broker="zerodha", status="connected",
            access_token=session_data["access_token"], kite_user_id=session_data.get("broker_user_id"),
            connected_at=now,
        )
        db.add(connection)
    else:
        connection.status = "connected"
        connection.access_token = session_data["access_token"]
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


async def get_portfolio(db: AsyncSession, *, user_id: uuid.UUID, adapter: BrokerAdapter | None = None) -> dict:
    """PF.4 — live, on-demand fetch (no cache/background sync in MVP,
    Architecture V2 §3). Any broker-side failure (expired token, Kite API
    error) is uniformly reported as `BROKER_AUTH_FAILED` per the locked
    error-code list (API Spec V2 §9 does not define separate codes for
    'expired' vs 'other API failure' — both are broker-side auth/connectivity
    problems from the caller's perspective, and the fix is the same either
    way: reconnect)."""
    connection = await get_connection_status_or_404(db, user_id=user_id)
    effective_adapter = _adapter_or_default(adapter)
    try:
        holdings = effective_adapter.fetch_holdings(access_token=connection.access_token)
        positions = effective_adapter.fetch_positions(access_token=connection.access_token)
    except BrokerConnectionError as e:
        raise QFinanceAPIError(
            "BROKER_AUTH_FAILED",
            "We couldn't reach Zerodha for your portfolio. Please reconnect your account.", 502,
        ) from e

    connection.last_synced_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "holdings": holdings, "positions": positions,
        "last_synced_at": connection.last_synced_at,
        "read_only_notice": "Read-only — Qfinera cannot place trades.",
    }
