"""AI BYOK connection routes.

Endpoints: connect (POST), status (GET), connections (GET, list), test-connection
(POST), disconnect (DELETE). Every endpoint requires an authenticated, VERIFIED
caller; `user_id` always comes from the session (never a path/query parameter),
so ownership is structural. Mutating routes require CSRF. `test-connection` is a
POST (it makes the server call out to a user-chosen URL) and is additionally
rate-limited inside the service.

No route here ever returns an API key (see schemas.py — no response schema has a
key-shaped field). There is deliberately still NO "ask the AI" route: provider
resolution for the Research Assistant lives in service.resolve_provider_for_user
and is not exposed over HTTP.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_csrf, require_verified_email
from app.core.errors import QFinanceAPIError
from app.modules.ai import service
from app.modules.ai.models import VALID_PROVIDERS
from app.modules.ai.schemas import ConnectRequest, StatusResponse, TestConnectionRequest, TestConnectionResponse
from app.modules.auth.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/connect", response_model=StatusResponse, dependencies=[Depends(require_csrf)])
async def ai_connect(
    body: ConnectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    connection = await service.connect(
        db, user_id=user.id, provider=body.provider, api_key=body.api_key,
        endpoint=body.endpoint, model=body.model,
    )
    return StatusResponse(
        connected=True, provider=connection.provider, connected_at=connection.connected_at,
        endpoint=connection.endpoint, model=connection.model,
    )


@router.get("/status", response_model=StatusResponse)
async def ai_status(
    provider: str = "anthropic",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    if provider not in VALID_PROVIDERS:
        # A status check for an unsupported provider is a clean 400, not a silent "not connected".
        raise QFinanceAPIError("INVALID_AI_PROVIDER", f"provider must be one of {VALID_PROVIDERS}.", 400)
    result = await service.get_status(db, user_id=user.id, provider=provider)
    return StatusResponse(**result)


@router.get("/connections", response_model=list[StatusResponse])
async def ai_connections(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    """The caller's own connections, most recently connected first — the first
    entry is the 'active' one the Research Assistant will use."""
    return [StatusResponse(**row) for row in await service.list_connections(db, user_id=user.id)]


@router.post("/test-connection", response_model=TestConnectionResponse, dependencies=[Depends(require_csrf)])
async def ai_test_connection(
    body: TestConnectionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    result = await service.check_connection(
        db, user_id=user.id, provider=body.provider, api_key=body.api_key,
        endpoint=body.endpoint, model=body.model,
    )
    return TestConnectionResponse(**result)


@router.delete("/connect", status_code=204, dependencies=[Depends(require_csrf)])
async def ai_disconnect(
    provider: str = "anthropic",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    await service.disconnect(db, user_id=user.id, provider=provider)
