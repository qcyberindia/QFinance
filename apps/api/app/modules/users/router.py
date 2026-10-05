"""users module routes — compliance acknowledgment (§4.5.1/§4.5.2) and the
member's own profile (GET/PATCH /users/me/profile, Profile Control Center).
Every route acts on the session's user only; no user id is ever accepted.
WRITTEN, NOT EXECUTED."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_csrf
from app.modules.auth.models import User
from app.modules.users import service

router = APIRouter(prefix="/users", tags=["users"])


class AcknowledgeRiskDisclosureRequest(BaseModel):
    context: str  # "signup" | "first_payment" — validated in service.py


class AcknowledgmentResponse(BaseModel):
    acknowledged_at: str


@router.post("/me/acknowledge-charter", response_model=AcknowledgmentResponse, dependencies=[Depends(require_csrf)])
async def acknowledge_charter(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    ack = await service.acknowledge_charter(db, user_id=user.id)
    return AcknowledgmentResponse(acknowledged_at=ack.acknowledged_at.isoformat())


@router.post(
    "/me/acknowledge-risk-disclosure", response_model=AcknowledgmentResponse, dependencies=[Depends(require_csrf)]
)
async def acknowledge_risk_disclosure(
    body: AcknowledgeRiskDisclosureRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ack = await service.acknowledge_risk_disclosure(db, user_id=user.id, context=body.context)
    return AcknowledgmentResponse(acknowledged_at=ack.acknowledged_at.isoformat())


class MyProfileResponse(BaseModel):
    """Own profile. `name` and `email` are private — returned only to the
    member themself, never by the public profile (profile module)."""
    username: str
    bio: str | None
    experience_level: str | None
    name: str
    email: str
    email_verified: bool
    joined_at: datetime
    published_posts_count: int
    published_theses_count: int
    contribution_points: int


class MyProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # e.g. email/role_grants are rejected, not ignored

    name: str | None = None
    username: str | None = None
    bio: str | None = None
    experience_level: str | None = None


@router.get("/me/profile", response_model=MyProfileResponse)
async def get_my_profile(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await service.get_my_profile(db, user=user)


@router.patch("/me/profile", response_model=MyProfileResponse, dependencies=[Depends(require_csrf)])
async def update_my_profile(
    body: MyProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await service.update_my_profile(db, user=user, changes=body.model_dump(exclude_unset=True))
