"""Research Workspace sections 06 (Management) and 07 (Assumptions &
Outlook) — additive-only columns on `research`.

Both are genuinely required: the 13-section Research Workspace UI requests
these two sections as real, persisted, editable content, and no existing
column can hold them (they are semantically distinct from every QRES stage
field already in the table). Free text, nullable, no default, no scoring,
no AI-generated content — same pattern as every other Q-RESEARCH stage
column (0001_initial_schema.py).

Per the project's additive-only migration principle (Database Schema V1
§15.1): this ADDS two nullable columns to the existing `research` table. It
does not alter, rename, or drop any existing column, and does not touch
QRES_STAGE_FIELDS (business_quality..invalidation_conditions), which remain
exactly as locked.

WRITTEN, NOT EXECUTED — no real database has been reached in this session;
this migration has not been run against any host. Verify with
`alembic upgrade head` on a real database before relying on these columns.

GRAPH UPDATE (this pass): `down_revision` changed from `"0006_contrib"` to
`"0006_repair"`. `0006_contribution_idempotency.py` (id `"0006_contrib"`)
has been removed from `alembic/versions/` — it could not remain a valid
graph node once the confirmed real database state required a corrective
migration (`0006_repair`) chained directly after `"0006"` instead; see
`0006_repair.py`'s docstring for the full reasoning and the original
file's content preserved verbatim there.

Revision ID: 0007
Revises: 0006_repair
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
# RESOLVED this pass (superseding the previous resolution note below, kept
# for history): the two migrations previously sharing revision id "0006"
# were a literal duplicate revision ID. The first fix (renumbering one to
# "0006_contrib" and chaining it after "0006") turned out to be graph-legal
# but did not match the real database, which had already executed the
# contribution-idempotency body under the shared "0006" id before the fix
# existed. `0006_repair.py` (down_revision="0006") is the corrected fix,
# reconciling that real state via runtime inspection rather than replaying
# `0006_contrib`'s upgrade() unconditionally. The graph is now:
# 0005 -> 0006 (ai_research_assistant) -> 0006_repair -> 0007 (this file).
down_revision = "0006_repair"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research", sa.Column("management_notes", sa.Text(), nullable=True))
    op.add_column("research", sa.Column("assumptions_outlook", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("research", "assumptions_outlook")
    op.drop_column("research", "management_notes")
