"""Q-Points routes. Mounted at the existing `/credits` prefix (API Spec V2
§8, C.1) so current clients keep working, but the response is a points score
and contribution history only — Q-Points have no monetary value."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.modules.auth.models import User
from app.modules.contributions import service
from app.modules.contributions.schemas import QPointsSummaryResponse

router = APIRouter(prefix="/credits", tags=["q-points"])


@router.get("/me", response_model=QPointsSummaryResponse)
async def get_my_q_points(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.get_points_summary(db, user_id=user.id, page=page, page_size=page_size)
