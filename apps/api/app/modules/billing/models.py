"""payments + invoices tables — Architecture §5.3, Database Schema V1 §5/§6,
PAY-001-006, OD-16, ERR-003.
Column-for-column match against alembic/versions/0001_initial_schema.py.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("status IN ('pending','succeeded','failed','refunded')", name="ck_payments_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False
    )
    amount_paise: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String, nullable=False)
    # UNIQUE — this is the webhook-idempotency mechanism (ERR-003), not incidental.
    gateway_reference_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    billing_period_start: Mapped[datetime] = mapped_column(nullable=False)
    billing_period_end: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("payments.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(nullable=False)
    # OD-16 pending legal/accounting finalization — always 0 until TaxService is given
    # a real GST/HSN-SAC treatment to apply (see integrations/invoice_service.py).
    tax_paise: Mapped[int] = mapped_column(nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    payment_status: Mapped[str] = mapped_column(String, nullable=False)
    invoice_date: Mapped[date] = mapped_column(nullable=False)
    billing_period: Mapped[str] = mapped_column(Text, nullable=False)
    gateway_reference: Mapped[str] = mapped_column(Text, nullable=False)
    tax_treatment_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
