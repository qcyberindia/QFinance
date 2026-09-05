"""research / research_versions / research_sources / research_tags —
Architecture §5.3/AD-16/AD-17/AD-18, Database Schema V1 §8/§9/§10.
Column set matches alembic/versions/0001_initial_schema.py exactly — no
columns invented here that aren't already in the migration.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

# QRES-001/002 — the nine Q-RESEARCH stage fields (bull/base/bear are three
# separate columns per the migration, not one combined field).
QRES_STAGE_FIELDS = (
    "business_quality", "financial_snapshot", "business_model", "competitive_position",
    "valuation_range", "bull_case", "base_case", "bear_case", "risk_register",
    "catalysts", "invalidation_conditions",
)

PLACEHOLDER_TITLE = "Untitled research"
PLACEHOLDER_SUMMARY = ""


class Research(Base):
    __tablename__ = "research"
    __table_args__ = (
        CheckConstraint("status IN ('draft','published')", name="ck_research_status"),
        CheckConstraint("moderation_status IN ('active','restricted','removed')", name="ck_research_mod_status"),
        CheckConstraint("access_tier IN ('core','free_example')", name="ck_research_access_tier"),
        # Database Schema V1 §8 — added via alembic/versions/0002_research_fts_and_length_checks.py
        CheckConstraint("char_length(title) BETWEEN 1 AND 200", name="ck_research_title_length"),
        CheckConstraint("char_length(summary) BETWEEN 1 AND 500", name="ck_research_summary_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    research_type: Mapped[str] = mapped_column(String, nullable=False)
    industry: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    moderation_status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    access_tier: Mapped[str] = mapped_column(String, nullable=False, default="core")  # AD-18
    title: Mapped[str] = mapped_column(Text, nullable=False, default=PLACEHOLDER_TITLE)  # AD-16
    summary: Mapped[str] = mapped_column(Text, nullable=False, default=PLACEHOLDER_SUMMARY)  # AD-16
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    business_quality: Mapped[str | None] = mapped_column(Text, nullable=True)
    financial_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitive_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    valuation_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    bull_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    bear_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_register: Mapped[str | None] = mapped_column(Text, nullable=True)
    catalysts: Mapped[str | None] = mapped_column(Text, nullable=True)
    invalidation_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SRC-003/004 — explicit tri-state: NULL = unanswered, True/False = answered.
    conflict_disclosed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    conflict_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    position_disclosed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    position_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ResearchVersion(Base):
    """Immutable snapshot, inserted on every publish or post-publish edit
    (VER-001/002/003/004). Never updated or deleted after insert."""

    __tablename__ = "research_versions"
    __table_args__ = (
        UniqueConstraint("research_id", "version_number", name="ux_research_versions_research_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("research.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_note: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ResearchSource(Base):
    """SRC-001/002 — at least one row required to publish (enforced in
    service.py, not by a DB constraint, since a draft may have zero)."""

    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("research.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    supports_claim: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ResearchTag(Base):
    __tablename__ = "research_tags"
    __table_args__ = (UniqueConstraint("research_id", "tag", name="ux_research_tags_research_tag"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    research_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("research.id"), nullable=False)
    tag: Mapped[str] = mapped_column(CITEXT, nullable=False)
