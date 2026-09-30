"""Allow empty summary for research drafts.

The Research model intentionally uses an empty summary as the initial
draft placeholder. Keep the existing 500-character upper bound.

GRAPH FIX (this pass): this file previously declared `revision = "0008"`,
identical to `0008_ai_connections_add_openai_provider.py`'s own
`revision = "0008"` — a duplicate revision id, the same bug class fixed at
"0006"/"0006_contrib" earlier in this project's history. Renumbered to
`"0008_summary"` and re-chained after `"0008"` (a linear ordering pick, not
a true merge — these two migrations touch entirely disjoint tables,
`research` vs `ai_connections`, so there is nothing to actually merge).
Safe to do as a simple renumber (not a corrective-migration-with-
introspection like `0006_repair.py` needed): unlike the 0006 case, no
evidence exists that either 0008 file has been applied to the real
database under the colliding id — the database was still confirmed at
revision `0006` as of this same session, several migrations behind either
0008 file, so no drift has had a chance to occur here. Operator should
still confirm via `alembic current` before running `upgrade head`, as a
matter of course, not because specific contrary evidence exists.

WRITTEN, NOT EXECUTED.

Revision ID: 0008_summary
Revises: 0008
Create Date: 2026-09-26
"""

from alembic import op

revision = "0008_summary"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_research_summary_length",
        "research",
        type_="check",
    )
    op.create_check_constraint(
        "ck_research_summary_length",
        "research",
        "char_length(summary) BETWEEN 0 AND 500",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_research_summary_length",
        "research",
        type_="check",
    )
    op.create_check_constraint(
        "ck_research_summary_length",
        "research",
        "char_length(summary) BETWEEN 1 AND 500",
    )
