"""Credits routes — API Specification V2 §8 (C.1). WRITTEN, NOT EXECUTED."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.auth.models import User
from app.modules.contributions import service
from app.modules.contributions.schemas import CreditLedgerEntryResponse, CreditsSummaryResponse

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/me", response_model=CreditsSummaryResponse)
async def get_my_credits(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    summary = await service.get_credits_summary(db, user_id=user.id, page=page, page_size=page_size)
    return CreditsSummaryResponse(
        balance_paise=summary["balance_paise"], page=summary["page"], page_size=summary["page_size"],
        total=summary["total"], entries=[CreditLedgerEntryResponse.model_validate(e) for e in summary["entries"]],
    )
