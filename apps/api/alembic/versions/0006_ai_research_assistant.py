"""AI Research Assistant (BYOK) — ai_connections + research_notes tables.

SCOPE NOTE, stated explicitly: this migration implements only what the
"core loop first" MVP needs (Question -> AI Answer -> Save -> Context ->
Next Question). It does NOT add a table for auto-generated "suggested
questions" or a "Research Brief" object — both are deferred (see
work_memory.md); the core loop persists real user-asked questions and real
AI answers, which is sufficient for the requested priority order.

SECURITY FIX (this pass): `ai_connections` now stores `encrypted_api_key`
(Fernet ciphertext, see app/core/crypto.py) instead of a plaintext
`api_key` column. An earlier version of this migration stored the
member's BYOK provider key in plaintext, matching
`broker_connections.access_token`'s known-and-flagged gap — that tradeoff
was wrong for a value this sensitive and is corrected here, not carried
forward.

Edited IN PLACE rather than shipped as a new 0007 rename migration,
because this migration has never been applied to any real database: per
work_memory.md, `alembic current` was last host-confirmed at `0003`, and
0004/0005/0006 have never been run by any session with genuine database
execution access. Editing a still-unexecuted migration is the correct fix
here; renaming a column out from under real data would not be.

If this migration WAS applied to some real database outside the sessions
work_memory.md accounts for, this in-place edit is NOT sufficient by
itself: `alembic upgrade` would fail against that database (the old
`api_key` column already exists; this revision no longer creates it), and
any row already written there is genuinely plaintext data this file cannot
discover or fix automatically. That scenario requires manual, human-
verified remediation: confirm via `\d ai_connections` on that specific
database whether the column is `api_key` or `encrypted_api_key`, and if
`api_key` with existing rows, write a one-off migration that adds
`encrypted_api_key`, encrypts each existing plaintext value with the
currently-configured `AI_KEY_ENCRYPTION_SECRET` via
`app.core.crypto.encrypt_secret`, drops `api_key`, and is run and verified
by hand — this must not be automated speculatively here against a scenario
with no confirmed evidence it has occurred.

WRITTEN, NOT EXECUTED.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),  # Fernet ciphertext only, see app/core/crypto.py
        sa.Column("connected_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('anthropic')", name="ck_ai_connections_provider"),
        sa.UniqueConstraint("user_id", "provider", name="ux_ai_connections_user_provider"),
    )

    op.create_table(
        "research_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("research_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("target_field", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "target_field IS NULL OR target_field IN "
            "('business_quality','financial_snapshot','business_model','competitive_position',"
            "'valuation_range','bull_case','base_case','bear_case','risk_register','catalysts',"
            "'invalidation_conditions','summary')",
            name="ck_research_notes_target_field",
        ),
    )
    op.create_index("ix_research_notes_research_id", "research_notes", ["research_id"])


def downgrade() -> None:
    op.drop_index("ix_research_notes_research_id", table_name="research_notes")
    op.drop_table("research_notes")
    op.drop_table("ai_connections")
