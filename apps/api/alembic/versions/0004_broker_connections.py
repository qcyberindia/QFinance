"""Add broker_connections table — Database Schema V2 §1, Portfolio module
(API Specification V2 §7, PF.1-PF.4). Additive-only migration, no existing
table touched.

SCOPE NOTE: this migration covers ONLY `broker_connections` (Portfolio).
Database Schema V2 §1/§2 also specifies `ratings`, `contributions`,
`credit_ledger` (new tables) and `posts.post_type`/`comments.parent_comment_id`
(new columns on existing tables) — none of those are part of this migration,
since this session's scope was specifically the Portfolio module. They remain
open, pre-existing gaps for whichever future session implements Community's
V2 delta / Ratings / Contributions — flagged in work_memory.md, not silently
bundled into this migration nor silently ignored.

WRITTEN, NOT EXECUTED — `alembic upgrade head` has not been run against a
real PostgreSQL instance in this session.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "broker_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("broker", sa.Text(), nullable=False, server_default="zerodha"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("kite_user_id", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("broker = 'zerodha'", name="ck_broker_connections_broker"),
        sa.CheckConstraint("status IN ('connected','disconnected','error')", name="ck_broker_connections_status"),
        sa.UniqueConstraint("user_id", "broker", name="ux_broker_connections_user_broker"),
    )


def downgrade() -> None:
    op.drop_table("broker_connections")
