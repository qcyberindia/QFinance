"""BYOK AI Research Assistant — models.
WRITTEN, NOT EXECUTED.

Two tables, both new (genuinely necessary — no existing table can hold a
per-user encrypted API key or accumulated Q&A research context):

`ai_provider_keys` — one row per (user, provider). The key itself is stored
ENCRYPTED (see service.py's Fernet usage) — never plaintext, never returned
by any API response, never logged.

`research_context_entries` — one row per question asked against a specific
research item. `added_to_research` marks whether the user chose to pull this
answer into the actual Research document (via the EXISTING research PATCH
endpoint — this table does not duplicate research content storage, it only
records the Q&A history and which entries the user acted on).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

SUPPORTED_PROVIDERS = ("openai",)  # MVP: one real provider; abstraction supports more later


class AiProviderKey(Base):
    __tablename__ = "ai_provider_keys"
    __table_args__ = (
        CheckConstraint(f"provider IN {SUPPORTED_PROVIDERS}", name="ck_ai_provider_keys_provider"),
        UniqueConstraint("user_id", "provider", name="ux_ai_provider_keys_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class ResearchContextEntry(Base):
    __tablename__ = "research_context_entries"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("research.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    added_to_research: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    added_to_field: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
