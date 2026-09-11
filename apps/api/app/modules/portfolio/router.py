"""Portfolio routes — API Specification V2 §7 (PF.1-PF.4).

Every endpoint requires an authenticated caller and every operation is
scoped to that caller's own connection/portfolio only (`user_id` always
comes from the session, never from a path/query parameter) — matching this
task's explicit "a user must only be able to access their own portfolio"
requirement structurally, not by a convention that could be forgotten.

WRITTEN, NOT EXECUTED.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_csrf, require_verified_email
from app.modules.auth.models import User
from app.modules.portfolio import service
from app.modules.portfolio.schemas import ConnectionStatusResponse, ConnectResponse, PortfolioResponse

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/zerodha/connect", response_model=ConnectResponse)
async def zerodha_connect(user: User = Depends(require_verified_email)):
    login_url = await service.get_login_url()
    return ConnectResponse(login_url=login_url)


@router.get("/zerodha/callback", response_model=ConnectionStatusResponse)
async def zerodha_callback(
    request_token: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    connection = await service.complete_connection(db, user_id=user.id, request_token=request_token)
    return ConnectionStatusResponse(
        broker=connection.broker, status=connection.status,
        connected_at=connection.connected_at, last_synced_at=connection.last_synced_at,
    )


@router.delete("/zerodha", status_code=204, dependencies=[Depends(require_csrf)])
async def zerodha_disconnect(db: AsyncSession = Depends(get_db), user: User = Depends(require_verified_email)):
    await service.disconnect(db, user_id=user.id)


@router.get("", response_model=PortfolioResponse)
async def get_portfolio(db: AsyncSession = Depends(get_db), user: User = Depends(require_verified_email)):
    result = await service.get_portfolio(db, user_id=user.id)
    return PortfolioResponse(**result)
