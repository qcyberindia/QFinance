"""Journal module models — API Specification V2 §1, Database Schema V2 §1.
WRITTEN, NOT EXECUTED.

Private-only by design: no other module imports this model, and this module
never imports community/research models — the isolation itself is the
compliance control (PRD V2 §4.2: 'never queryable or joinable by any
Community-facing endpoint'), not just a comment promising it.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

VALID_ENTRY_TYPES = ("decision", "reasoning", "observation", "note")


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        CheckConstraint(f"entry_type IN {VALID_ENTRY_TYPES}", name="ck_journal_entries_type"),
        CheckConstraint("char_length(content) BETWEEN 1 AND 10000", name="ck_journal_entries_content_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
