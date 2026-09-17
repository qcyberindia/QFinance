"""Pydantic schemas — portfolio module, API Specification V2 §7 (PF.1-PF.4).

SECURITY NOTE, restated at the schema layer (not just the model layer):
`access_token` does not appear in ANY schema in this file, request or
response — there is no field name here that could accidentally leak it via a
future careless `response_model` change, because the field simply isn't
defined anywhere in this module's Pydantic surface at all.

WRITTEN, NOT EXECUTED.
"""
from datetime import datetime

from pydantic import BaseModel


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


class HoldingItem(BaseModel):
    """Deliberately a permissive passthrough of Kite's own holding fields
    (trading_symbol/quantity/average_price/last_price/pnl/etc.) rather than a
    strict allow-list — Kite's API surface for holdings is the source of
    truth for what a holding contains; QFinance doesn't compute or infer any
    of these values itself (PRD V2 §4.1: 'read-only view')."""
    trading_symbol: str
    quantity: float
    average_price: float
    last_price: float | None = None
    pnl: float | None = None
    exchange: str | None = None


class PositionItem(BaseModel):
    trading_symbol: str
    quantity: float
    average_price: float | None = None
    last_price: float | None = None
    pnl: float | None = None
    exchange: str | None = None


class PortfolioResponse(BaseModel):
    """PF.4. `last_synced_at` reflects this on-demand fetch's own timestamp
    (MVP has no background sync, per Architecture V2 §3 — 'no scheduled sync
    job'), not a cached/stale value from a prior request."""
    holdings: list[HoldingItem]
    positions: list[PositionItem]
    last_synced_at: datetime
    read_only_notice: str = "Read-only — Qfinera cannot place trades."
