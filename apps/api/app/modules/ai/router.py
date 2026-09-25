"""AI BYOK connection routes.

FINDING, stated explicitly (not silently fixed by inventing scope): before
this pass, app/modules/ai/ had models.py/schemas.py/service.py but no
router.py, and was not mounted in app/api/v1/router.py — the BYOK
connect/status/disconnect endpoints did not exist as "existing API paths"
to preserve, despite that being how this task was framed. This file adds
the minimal router needed to (a) make app/modules/ai/service.py reachable
at all, and (b) make the requested API-level tests (response never exposes
the raw key, connect/update stores encrypted key, disconnect works, user
isolation) meaningful against real endpoints rather than only against
service functions directly. No behavior beyond connect/status/disconnect is
added here — the separate "ask the AI a question" flow implied by
research_notes (migration 0006) has no service/router of its own and is
NOT implemented by this file; that remains out of scope.

Pattern mirrors app/modules/portfolio/router.py exactly: every endpoint
requires an authenticated, verified caller; `user_id` always comes from the
session (never a path/query parameter), so ownership is structural, not a
convention that could be forgotten; mutating routes require CSRF.

WRITTEN, NOT EXECUTED.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import require_csrf, require_verified_email
from app.core.errors import QFinanceAPIError
from app.modules.ai import service
from app.modules.ai.models import VALID_PROVIDERS
from app.modules.ai.schemas import ConnectRequest, StatusResponse
from app.modules.auth.models import User

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/connect", response_model=StatusResponse, dependencies=[Depends(require_csrf)])
async def ai_connect(
    body: ConnectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    connection = await service.connect(db, user_id=user.id, provider=body.provider, api_key=body.api_key)
    return StatusResponse(connected=True, provider=connection.provider, connected_at=connection.connected_at)


@router.get("/status", response_model=StatusResponse)
async def ai_status(
    provider: str = "anthropic",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    if provider not in VALID_PROVIDERS:
        # Same shape as service.connect's own validation — a status check for
        # an unsupported provider is a clean 400, not a silent "not connected".
        raise QFinanceAPIError("INVALID_AI_PROVIDER", f"provider must be one of {VALID_PROVIDERS}.", 400)
    result = await service.get_status(db, user_id=user.id, provider=provider)
    return StatusResponse(**result)


@router.delete("/connect", status_code=204, dependencies=[Depends(require_csrf)])
async def ai_disconnect(
    provider: str = "anthropic",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    await service.disconnect(db, user_id=user.id, provider=provider)
