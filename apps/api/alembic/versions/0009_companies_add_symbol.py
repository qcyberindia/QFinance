"""Add companies.symbol (nullable) — the exchange ticker (e.g. "TATAPOWER"),
required by the Research Subject feature (Research Phase 3) to show a
company's symbol alongside its name. See companies/models.py's own docstring
for why this was judged genuinely required rather than optional scope.

Purely additive: one nullable column, no data touched, no other table
affected, no constraint on existing rows.

WRITTEN, NOT EXECUTED.

GRAPH UPDATE (this pass): `down_revision` changed from `"0008"` to
`"0008_summary"` — `0008` briefly collided with a second migration also
claiming that id (`0008_research_summary_empty_allowed.py`, renumbered to
`0008_summary`); see that file's own docstring. Graph is now:
0007 -> 0008 (openai provider) -> 0008_summary (research summary) -> 0009 (this file).

Revision ID: 0009
Revises: 0008_summary
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("symbol", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "symbol")
