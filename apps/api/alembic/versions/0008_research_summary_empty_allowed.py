"""Allow empty summary for research drafts.

The Research model intentionally uses an empty summary as the initial
draft placeholder. Keep the existing 500-character upper bound.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
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
