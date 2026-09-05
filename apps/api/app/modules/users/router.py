"""users module routes — this pass only wires §4.5.1/§4.5.2 (compliance
acknowledgment), the prerequisite for community's charter gate. §2's profile
endpoints remain unbuilt — see service.py's module docstring.
WRITTEN, NOT EXECUTED."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
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
