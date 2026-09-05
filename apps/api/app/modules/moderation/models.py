"""Moderation module models — API Specification V1 §5, PRD MOD-001-005,
Architecture §10.1/AD-08. WRITTEN, NOT EXECUTED.

`ModerationAction` and `ModerationRule` map onto tables Architecture §4.2's
module-ownership table assigns directly to `moderation` (`moderation_rules`,
`moderation_actions`) — both tables already exist in
alembic/versions/0001_initial_schema.py; no new migration is needed here.

`Report`, however, sits on a table Architecture §4.2 nominally assigns to
`community` ("community | owns: posts, comments, reactions, reports,
bookmarks"). No `Report` ORM model exists anywhere in the codebase yet —
community/service.py only ever INSERTs into `reports` via raw SQL for its
narrow MOD-003 auto-flagging use case, and never reads/updates the table.
Since `moderation` is the module that actually needs full CRUD (create,
queue-list, resolve) against `reports`, defining the ORM model here — rather
than in community/models.py, which would need no changes to support its own
existing raw-SQL-only usage — is the pragmatic choice for this task: it
avoids touching community/models.py for a table community's own code doesn't
otherwise need an ORM model for, while giving moderation the single query
surface API Spec §5.1-5.3 actually requires. This is a deliberate,
documented deviation from Architecture §4.2's table-ownership *column*
placement, not an accidental one — flagged here and in work_memory.md.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

REPORT_TARGET_TYPES = ("post", "comment", "research")
MODERATION_ACTION_TARGET_TYPES = ("post", "comment", "research", "member")
MODERATION_ACTIONS = ("approve", "edit", "restrict", "remove", "reinstate", "suspend_member", "reinstate_member")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(f"target_type IN {REPORT_TARGET_TYPES}", name="ck_reports_target_type"),
        CheckConstraint("status IN ('open','resolved')", name="ck_reports_status"),
        CheckConstraint(
            "resolution_action IS NULL OR resolution_action IN "
            "('approved','edited','restricted','removed','member_suspended')",
            name="ck_reports_resolution_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    resolution_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class ModerationAction(Base):
    __tablename__ = "moderation_actions"
    __table_args__ = (
        CheckConstraint(f"target_type IN {MODERATION_ACTION_TARGET_TYPES}", name="ck_mod_actions_target_type"),
        CheckConstraint(f"action IN {MODERATION_ACTIONS}", name="ck_mod_actions_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    moderator_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    report_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("reports.id"), nullable=True)
    previous_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_state: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class ModerationRule(Base):
    __tablename__ = "moderation_rules"
    __table_args__ = (
        CheckConstraint("severity IN ('low','medium','high')", name="ck_mod_rules_severity"),
        CheckConstraint("action = 'flag_for_review'", name="ck_mod_rules_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phrase: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    action: Mapped[str] = mapped_column(Text, nullable=False, default="flag_for_review")
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
