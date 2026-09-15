"""Pydantic schemas — membership (API Specification V1 §3.1/§3.3, MEM-001/002/005/007).
WRITTEN, NOT EXECUTED."""
from datetime import datetime

from pydantic import BaseModel


class PlanResponse(BaseModel):
    code: str
    price_paise: int
    currency: str
    billing_interval: str

    class Config:
        from_attributes = True


class MembershipResponse(BaseModel):
    plan_code: str
    status: str
    current_period_end: datetime | None
    grace_period_ends_at: datetime | None
    canceled_at: datetime | None
    available_credit_paise: int = 0
    effective_next_period_price_paise: int | None = None


class CancelResponse(BaseModel):
    canceled: bool
    access_until: datetime | None
