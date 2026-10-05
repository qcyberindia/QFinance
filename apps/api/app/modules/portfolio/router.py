"""Portfolio routes — API Specification V2 §7 (PF.1-PF.4).

Every endpoint requires an authenticated caller and every operation is
scoped to that caller's own connection/portfolio only (`user_id` always
comes from the session, never from a path/query parameter) — matching this
task's explicit "a user must only be able to access their own portfolio"
requirement structurally, not by a convention that could be forgotten.

WRITTEN, NOT EXECUTED.
"""
import re

from fastapi import APIRouter, Cookie, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_csrf, require_verified_email
from app.modules.auth.models import User
from app.core.errors import QFinanceAPIError
from app.modules.portfolio import oauth_state, service
from app.modules.portfolio.schemas import (
    ConnectionInfoResponse, ConnectionStatusResponse, ConnectResponse, PortfolioResponse,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/zerodha/connect", response_model=ConnectResponse)
async def zerodha_connect(
    user: User = Depends(require_verified_email),
    qf_session: str = Cookie(default="", alias="qf_session"),
):
    """Issues a single-use OAuth state bound to this user + session and
    returns Kite's login URL carrying it (oauth_state.py)."""
    state = await oauth_state.create_state(user_id=user.id, session_token=qf_session)
    return ConnectResponse(login_url=await service.get_login_url(state=state))


_REQUEST_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{1,128}$")
_CALLBACK_REJECTED = "This Zerodha login link is invalid or has expired. Please connect again."


class ZerodhaCallbackRequest(BaseModel):
    # Plain strings, validated below: a schema-level pattern would make
    # FastAPI's 422 response echo the rejected value back to the client.
    request_token: str = ""
    state: str = ""


@router.post("/zerodha/callback", response_model=ConnectionStatusResponse, dependencies=[Depends(require_csrf)])
async def zerodha_callback(
    body: ZerodhaCallbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
    qf_session: str = Cookie(default="", alias="qf_session"),
):
    """Completes a Zerodha login. POST with a JSON body, so the one-time
    request_token never appears in a URL the API server logs. The OAuth
    state is checked (and consumed) BEFORE the token is sent to Kite."""
    if not await oauth_state.consume_state(state=body.state, user_id=user.id, session_token=qf_session):
        raise QFinanceAPIError("BROKER_STATE_INVALID", _CALLBACK_REJECTED, 400)
    if not _REQUEST_TOKEN_RE.match(body.request_token):
        raise QFinanceAPIError("BROKER_AUTH_FAILED", "Failed to connect your Zerodha account. Please try again.", 400)
    connection = await service.complete_connection(db, user_id=user.id, request_token=body.request_token)
    return ConnectionStatusResponse(
        broker=connection.broker, status=connection.status,
        connected_at=connection.connected_at, last_synced_at=connection.last_synced_at,
    )


@router.delete("/zerodha", status_code=204, dependencies=[Depends(require_csrf)])
async def zerodha_disconnect(db: AsyncSession = Depends(get_db), user: User = Depends(require_verified_email)):
    await service.disconnect(db, user_id=user.id)


@router.get("/connection", response_model=ConnectionInfoResponse)
async def get_connection_info(db: AsyncSession = Depends(get_db), user: User = Depends(require_verified_email)):
    """The caller's own connection state (never the token or broker account
    id) — lets the UI show connected / needs-reconnect without calling Kite."""
    connection = await service.get_connection(db, user_id=user.id)
    if connection is None:
        return ConnectionInfoResponse(broker="zerodha", status="not_connected", connected_at=None, last_synced_at=None)
    return ConnectionInfoResponse(
        broker=connection.broker, status=connection.status,
        connected_at=connection.connected_at, last_synced_at=connection.last_synced_at,
    )


@router.get("", response_model=PortfolioResponse)
async def get_portfolio(db: AsyncSession = Depends(get_db), user: User = Depends(require_verified_email)):
    result = await service.get_portfolio(db, user_id=user.id)
    return PortfolioResponse(**result)
