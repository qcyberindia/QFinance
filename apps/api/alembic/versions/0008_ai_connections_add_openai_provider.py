"""Widen ai_connections.provider from a single hardcoded value ('anthropic'
only) to an explicit two-value allow-list ('anthropic', 'openai') — see
app/modules/ai/models.py's own docstring (this same pass) for the product
reasoning (only providers with a real, already-written adapter are added;
Gemini/others are deliberately excluded since no adapter for them exists
anywhere in this repository).

This is a metadata-only constraint change: no column added/removed, no data
touched, no other table affected. Safe as an isolated migration because
0006/0006_contrib/0007 (everything this depends on) have never been applied
to a real database in any session so far (see their own docstrings) — but
unlike those, this migration makes NO assumption about whether THIS specific
migration itself has been run before being written; it uses DROP/ADD
CONSTRAINT IF EXISTS-safe operations either way, and downgrade() correctly
restores the original single-value constraint (destructive only in the sense
that any already-stored 'openai' row would violate it on downgrade — matches
the original constraint's own strictness, not a new risk introduced here).

WRITTEN, NOT EXECUTED.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_ai_connections_provider", "ai_connections", type_="check")
    op.create_check_constraint(
        "ck_ai_connections_provider", "ai_connections", "provider IN ('anthropic', 'openai')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_connections_provider", "ai_connections", type_="check")
    op.create_check_constraint(
        "ck_ai_connections_provider", "ai_connections", "provider = 'anthropic'",
    )
