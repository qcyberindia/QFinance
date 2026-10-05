"""Pydantic schemas — portfolio module, API Specification V2 §7 (PF.1-PF.4).

SECURITY NOTE, restated at the schema layer (not just the model layer):
`access_token` does not appear in ANY schema in this file, request or
response — there is no field name here that could accidentally leak it via a
future careless `response_model` change, because the field simply isn't
defined anywhere in this module's Pydantic surface at all.

WRITTEN, NOT EXECUTED.
"""
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator


def _as_utc(value: datetime | None) -> datetime | None:
    """broker_connections stores naive UTC; mark it as UTC on the way out so
    clients don't misread it as their local time."""
    return value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value


class ConnectResponse(BaseModel):
    """PF.1."""
    login_url: str


class ConnectionStatusResponse(BaseModel):
    """Returned by PF.2 (after callback) and available for status checks —
    deliberately the ONLY portfolio-connection-shaped response type, so
    PF.2/PF.3 can't accidentally diverge into returning different shapes for
    what is conceptually the same "connection state" answer."""
    broker: str
    status: str
    connected_at: datetime | None
    last_synced_at: datetime | None

    @field_validator("connected_at", "last_synced_at")
    @classmethod
    def _mark_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class ConnectionInfoResponse(BaseModel):
    """GET /portfolio/connection — connection state without calling the
    broker. `status` is 'not_connected' when no connection row exists."""
    broker: str
    status: str
    connected_at: datetime | None
    last_synced_at: datetime | None

    @field_validator("connected_at", "last_synced_at")
    @classmethod
    def _mark_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)


class HoldingItem(BaseModel):
    """A holding normalized from Kite's own fields (portfolio/service.py's
    normalize_holding). Values are the broker's numbers or arithmetic on
    them; None means 'not available', never an estimate."""
    trading_symbol: str
    exchange: str | None = None
    isin: str | None = None
    quantity: float
    t1_quantity: float = 0
    average_price: float | None = None
    last_price: float | None = None
    close_price: float | None = None
    invested_value: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    day_change_value: float | None = None
    day_change_percent: float | None = None
    allocation_percent: float | None = None


class PositionItem(BaseModel):
    trading_symbol: str
    exchange: str | None = None
    product: str | None = None
    quantity: float
    average_price: float | None = None
    last_price: float | None = None
    pnl: float | None = None


class PortfolioSummary(BaseModel):
    holdings_count: int
    invested_value: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    day_change_value: float | None = None
    day_change_percent: float | None = None
    top_holding_percent: float | None = None
    top_five_percent: float | None = None


class PortfolioResponse(BaseModel):
    """PF.4. `last_synced_at` is this on-demand fetch's own timestamp (no
    background sync in MVP, Architecture V2 §3)."""
    holdings: list[HoldingItem]
    positions: list[PositionItem]
    summary: PortfolioSummary
    last_synced_at: datetime
    read_only_notice: str = "Read-only — Qfinera cannot place trades."

    @field_validator("last_synced_at")
    @classmethod
    def _mark_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value)
