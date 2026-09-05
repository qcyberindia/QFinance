"""Pydantic schemas — billing (API Specification V1 §3.2/§3.4, PAY-001-006).
WRITTEN, NOT EXECUTED."""
from datetime import date

from pydantic import BaseModel


class CheckoutResponse(BaseModel):
    razorpay_order_id: str
    razorpay_key_id: str
    amount_paise: int


class InvoiceResponse(BaseModel):
    invoice_date: date
    amount_paise: int
    tax_paise: int
    billing_period: str
    payment_status: str

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    page: int
    page_size: int
    total: int
