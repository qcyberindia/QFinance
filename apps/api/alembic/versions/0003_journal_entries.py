"""Add journal_entries table — Database Schema V2 §1. Additive-only migration,
no existing table touched. WRITTEN, NOT EXECUTED — `alembic upgrade head` has
not been run against a real PostgreSQL instance in this session.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "entry_type IN ('decision','reasoning','observation','note')", name="ck_journal_entries_type",
        ),
        sa.CheckConstraint("char_length(content) BETWEEN 1 AND 10000", name="ck_journal_entries_content_length"),
    )
    op.create_index("ix_journal_entries_user", "journal_entries", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_journal_entries_user", table_name="journal_entries")
    op.drop_table("journal_entries")
