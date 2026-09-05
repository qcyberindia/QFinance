"""Membership routes — API Specification V1 §3.1/§3.3. Checkout/webhook/invoices
(payment side) live in `billing.router`, not here — this module owns plan/subscription
reads and cancellation only, per the module boundary in Architecture §4.2.
WRITTEN, NOT EXECUTED."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_csrf
from app.modules.auth.models import User
from app.modules.membership import service
from app.modules.membership.schemas import CancelResponse, MembershipResponse, PlanResponse

router = APIRouter(prefix="/membership", tags=["membership"])


@router.get("/plans", response_model=list[PlanResponse])
async def get_plans(db: AsyncSession = Depends(get_db)):
    plans = await service.get_plans(db)
    return [PlanResponse.model_validate(p) for p in plans]


@router.get("/me", response_model=MembershipResponse)
async def get_my_membership(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    membership = await service.get_my_membership(db, user.id)
    return MembershipResponse(**membership)


@router.post("/cancel", response_model=CancelResponse, dependencies=[Depends(require_csrf)])
async def cancel_membership(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subscription = await service.cancel_subscription(db, actor_id=user.id)
    return CancelResponse(canceled=True, access_until=subscription.current_period_end)
