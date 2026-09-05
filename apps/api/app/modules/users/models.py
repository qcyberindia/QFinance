"""profiles + compliance_acknowledgments tables — Architecture §5.3/AD-16, Database Schema V1.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import CITEXT, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "experience_level IS NULL OR experience_level IN ('beginner','intermediate','advanced')",
            name="ck_profiles_experience_level",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String, nullable=True)
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # Additive RBAC set (OD-05/RBAC-003) — TEXT[] per Architecture AD-02.
    role_grants: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=lambda: ["FREE_MEMBER"])
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    # No avatar_url column anywhere — OD-21/PROF-006.


class ComplianceAcknowledgment(Base):
    """CMPL-004/005 — Architecture AD-16. Append-only: no updated_at/deleted_at."""

    __tablename__ = "compliance_acknowledgments"
    __table_args__ = (
        CheckConstraint(
            "acknowledgment_type IN ('member_charter','risk_disclosure')",
            name="ck_compliance_ack_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    acknowledgment_type: Mapped[str] = mapped_column(String, nullable=False)
    document_version: Mapped[str] = mapped_column(String, nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
