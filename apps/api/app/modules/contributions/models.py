"""Contributions/Credits module models — Database Schema V2 §1 (contributions,
credit_ledger), Architecture V2 §7. Column set matches
alembic/versions/0005_v2_ratings_replies_credits.py exactly.
WRITTEN, NOT EXECUTED.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

SOURCE_TYPES = ("thesis_published", "engagement_received", "rating_received")


class Contribution(Base):
    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint(f"source_type IN {SOURCE_TYPES}", name="ck_contributions_source_type"),
        UniqueConstraint("actor_id", "source_type", "source_entity_id", name="ux_contributions_actor_event_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class CreditLedgerEntry(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    contribution_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contributions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
