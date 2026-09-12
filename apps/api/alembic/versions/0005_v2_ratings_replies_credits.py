"""V2 delta: posts.post_type, comments.parent_comment_id, ratings,
contributions, credit_ledger — Database Schema V2 §1/§2. Additive only, no
V1 table dropped/renamed, no historical migration touched.

WRITTEN, NOT EXECUTED — `alembic upgrade head` has not been run against a
real PostgreSQL instance in this session (see work_memory.md for the
tooling-access boundary: no tool in this session has execution access to
the real host).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("post_type", sa.Text(), nullable=False, server_default="general"),
    )
    op.create_check_constraint(
        "ck_posts_post_type", "posts", "post_type IN ('general','thesis','question','discussion')",
    )

    op.add_column(
        "comments",
        sa.Column("parent_comment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("comments.id"), nullable=True),
    )
    op.create_index("ix_comments_parent", "comments", ["parent_comment_id"])

    op.create_table(
        "ratings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("post_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_ratings_score"),
        sa.UniqueConstraint("user_id", "post_id", name="ux_ratings_user_post"),
    )

    op.create_table(
        "contributions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "source_type IN ('thesis_published','engagement_received','rating_received')",
            name="ck_contributions_source_type",
        ),
    )

    op.create_table(
        "credit_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("contribution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contributions.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("credit_ledger")
    op.drop_table("contributions")
    op.drop_table("ratings")
    op.drop_index("ix_comments_parent", table_name="comments")
    op.drop_column("comments", "parent_comment_id")
    op.drop_constraint("ck_posts_post_type", "posts", type_="check")
    op.drop_column("posts", "post_type")
