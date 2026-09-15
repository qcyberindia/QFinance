"""Profile routes — API Specification V2 §6 (P.1). WRITTEN, NOT EXECUTED."""
from fastapi import APIRouter, Depends

from app.core.db import get_db
from app.modules.profile import service
from app.modules.profile.schemas import PublicProfileResponse
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/{username}", response_model=PublicProfileResponse)
async def get_profile(username: str, db: AsyncSession = Depends(get_db)):
    """P.1 — public, no authentication required, per API Spec V2 §6."""
    profile = await service.get_public_profile(db, username=username)
    return PublicProfileResponse(**profile)
