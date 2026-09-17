"""Ratings routes — API Specification V2 §4 (R.1-R.3), mounted at
`/community/posts/{post_id}/rating(-summary)`. A second router sharing the
`/community` prefix, same technique already used for `research_discussion_router`
sharing `/research` with `research/router.py`.
WRITTEN, NOT EXECUTED."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_profile, require_csrf, require_verified_profile
from app.modules.ratings import service
from app.modules.ratings.schemas import RatingCreateRequest, RatingResponse, RatingSummaryResponse
from app.modules.users.models import Profile

router = APIRouter(prefix="/community", tags=["ratings"])


@router.post(
    "/posts/{post_id}/rating", response_model=RatingResponse, dependencies=[Depends(require_csrf)],
)
async def rate_post(
    post_id: uuid.UUID,
    body: RatingCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """Basic/Pro product decision (see require_verified_profile's docstring in
    core/deps.py) — rating a thesis no longer requires the old MEMBER role;
    Authenticated + Verified is sufficient, matching every other community
    participation action. Self-rating and post_type gates are unchanged,
    enforced in service.create_or_update_rating."""
    rating = await service.create_or_update_rating(db, actor_id=profile.user_id, post_id=post_id, score=body.score)
    return RatingResponse(post_id=str(rating.post_id), score=rating.score)


@router.delete("/posts/{post_id}/rating", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_rating(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    await service.remove_rating(db, actor_id=profile.user_id, post_id=post_id)


@router.get("/posts/{post_id}/rating-summary", response_model=RatingSummaryResponse)
async def rating_summary(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    summary = await service.get_rating_summary(db, post_id=post_id)
    return RatingSummaryResponse(**summary)
