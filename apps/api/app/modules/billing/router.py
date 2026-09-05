"""Billing routes — API Specification V1 §3.2/§3.4. Checkout requires Authenticated
+ Verified (§3.2.1's exact auth tier); invoices require only Authenticated (§3.4.1 —
no "+Verified" stated there, so `get_current_user` is used, not `require_verified_email`,
matching the spec's own distinction rather than applying the stricter tier everywhere
out of convenience). The webhook is CSRF-exempt and its own signature check is the
authentication (§3.2.2, §0.2) — no `get_current_user` dependency on that route at all.
WRITTEN, NOT EXECUTED."""
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user, require_csrf, require_verified_email
from app.modules.auth.models import User
from app.modules.billing import service
from app.modules.billing.schemas import CheckoutResponse, InvoiceListResponse, InvoiceResponse

router = APIRouter(tags=["billing"])


@router.post("/membership/checkout", response_model=CheckoutResponse, dependencies=[Depends(require_csrf)])
async def checkout(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_verified_email),
):
    result = await service.initiate_checkout(db, user_id=user.id)
    return CheckoutResponse(**result)


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
):
    raw_body = await request.body()
    result = await service.handle_webhook(db, raw_body=raw_body, signature=x_razorpay_signature or "")
    return result


@router.get("/membership/invoices", response_model=InvoiceListResponse)
async def list_invoices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await service.list_invoices(db, user_id=user.id, page=page, page_size=page_size)
    return InvoiceListResponse(
        items=[InvoiceResponse.model_validate(i) for i in items], page=page, page_size=page_size, total=total,
    )
