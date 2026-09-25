"""Repair migration — reconciles the duplicate-revision-id drift left by the
former `0006_contribution_idempotency.py` (which briefly shared the literal
revision id "0006" with this file's sibling, `0006_ai_research_assistant.py`).

WHY THIS FILE EXISTS, stated explicitly:

Two migrations were once both stamped `revision = "0006"`. At some point an
`alembic upgrade head` ran against a real database while both existed, and
under that id collision Alembic executed the CONTRIBUTION-IDEMPOTENCY body
(`ADD COLUMN contributions.actor_id`, backfill, `UNIQUE(actor_id,
source_type, source_entity_id)`) and stamped `alembic_version = '0006'`.
The AI-RESEARCH-ASSISTANT body (`CREATE TABLE ai_connections`, `CREATE
TABLE research_notes`) — which is what revision id "0006" is now defined to
mean, in `0006_ai_research_assistant.py` — never ran. This was confirmed by
direct, read-only inspection of the real database's `information_schema`
(not assumed): `alembic_version = 0006`; `contributions.actor_id` present;
`ai_connections` and `research_notes` both absent.

A prior pass renumbered the contribution-idempotency file to
`"0006_contrib"` and re-chained it after `"0006"`, which is graph-legal but
does not match the real database: a database honestly stamped `"0006"` by
Alembic's own bookkeeping, per that graph, has NOT yet run
`0006_contrib`'s `upgrade()` — but this one already has, in substance, just
under the wrong id. Running `alembic upgrade head` against it would attempt
`0006_contrib`'s `ADD COLUMN contributions.actor_id` again and fail with
`DuplicateColumnError` (this was independently reproduced and confirmed).

THE FIX: this migration sits directly after `"0006"` (matching the
database's honest, confirmed position) and does two things:
  1. Creates `ai_connections` and `research_notes` — the part of "0006" that
     is genuinely unapplied everywhere, copied byte-for-byte from
     `0006_ai_research_assistant.py`'s `upgrade()`.
  2. Reconciles `contributions.actor_id` and its uniqueness constraint by
     INSPECTING the live database at migration-run time (via SQLAlchemy's
     `Inspector`, not a blind `CREATE ... IF NOT EXISTS` clause) and only
     performing whichever of {add column + backfill, add constraint} is
     actually missing. This makes the migration correct on BOTH this
     specific drifted database (column present, constraint state to be
     confirmed by the operator's own read-only check before running) AND
     any other database that reaches this point in the graph for the first
     time with neither present at all — a single migration file, not two
     divergent code paths per environment.

The former `0006_contribution_idempotency.py` (revision id `"0006_contrib"`)
is REMOVED from `alembic/versions/` by this same change, not rewritten in
place. It cannot remain in the active graph: this file's `down_revision`
is `"0006"` (matching the database's real, confirmed position), so a
sibling file also claiming `down_revision = "0006"` would fork the graph
into two branches, and — since nothing would revise from it once `0007`'s
`down_revision` points here instead — `0006_contrib` would become a second,
orphaned head. Its full original content is preserved verbatim below for
provenance, not lost:

    -----------------------------------------------------------------
    ORIGINAL 0006_contribution_idempotency.py, revision "0006_contrib",
    down_revision "0006", verbatim, for historical record only —
    NOT executed by this file; its intent is folded into
    `_reconcile_contributions_actor_id()` below, made idempotent.
    -----------------------------------------------------------------

    def upgrade() -> None:
        op.add_column(
            "contributions",
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        )
        op.execute("UPDATE contributions SET actor_id = user_id WHERE actor_id IS NULL")
        op.alter_column("contributions", "actor_id", nullable=False)

        op.create_unique_constraint(
            "ux_contributions_actor_event_target",
            "contributions",
            ["actor_id", "source_type", "source_entity_id"],
        )

    def downgrade() -> None:
        op.drop_constraint("ux_contributions_actor_event_target", "contributions", type_="unique")
        op.drop_column("contributions", "actor_id")

    -----------------------------------------------------------------

No existing data is touched destructively anywhere in this file: the
`ai_connections`/`research_notes` tables are pure `CREATE TABLE` (nothing to
collide with, confirmed empty by the same inspection above); the
`contributions.actor_id` path only backfills from `user_id` for rows where
`actor_id IS NULL` (a no-op if the column already has values, which it does
on this database), and only adds the column/constraint when genuinely
absent, checked, not assumed.

`0007_research_management_and_assumptions.py` is updated in this same pass
to declare `down_revision = "0006_repair"` instead of `"0006_contrib"`.

WRITTEN, NOT EXECUTED — the operator must run the Step 1 read-only
constraint-inspection query and review this file before running
`alembic upgrade head`.

Revision ID: 0006_repair
Revises: 0006
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_repair"
down_revision = "0006"
branch_labels = None
depends_on = None


def _reconcile_contributions_actor_id() -> None:
    """Genuine runtime introspection, not a blind IF NOT EXISTS: checks the
    live database's actual columns and unique constraints on
    `contributions` and performs only whichever step is truly missing."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {c["name"] for c in inspector.get_columns("contributions")}
    if "actor_id" not in existing_columns:
        op.add_column(
            "contributions",
            sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        )
        op.execute("UPDATE contributions SET actor_id = user_id WHERE actor_id IS NULL")
        op.alter_column("contributions", "actor_id", nullable=False)
    # else: confirmed already present on this database (drift from the old
    # colliding-id execution) — column and its backfilled values are left
    # untouched, per explicit instruction to preserve existing data.

    existing_unique_constraints = inspector.get_unique_constraints("contributions")
    target_columns = ["actor_id", "source_type", "source_entity_id"]
    already_has_target_constraint = any(
        uc["column_names"] == target_columns or uc.get("name") == "ux_contributions_actor_event_target"
        for uc in existing_unique_constraints
    )
    if not already_has_target_constraint:
        op.create_unique_constraint(
            "ux_contributions_actor_event_target",
            "contributions",
            target_columns,
        )
    # else: constraint already present — not duplicated.


def upgrade() -> None:
    # --- Part 1: the genuinely-never-applied-anywhere part of "0006" ---
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

    # --- Part 2: reconcile the drifted contribution-idempotency changes ---
    _reconcile_contributions_actor_id()


def downgrade() -> None:
    """Symmetric best-effort reversal. Does not attempt to distinguish
    'this constraint/column existed before this migration ran' from 'this
    migration itself created it' — on downgrade, both are removed, matching
    the original two migrations' own downgrade() bodies combined. If this
    migration's upgrade() found the column/constraint already present
    (this database's actual case) and did nothing for that part, this
    downgrade() still drops it — consistent with 0006_contrib's own
    original downgrade() semantics, which this migration inherits."""
    op.drop_constraint("ux_contributions_actor_event_target", "contributions", type_="unique")
    op.drop_column("contributions", "actor_id")
    op.drop_index("ix_research_notes_research_id", table_name="research_notes")
    op.drop_table("research_notes")
    op.drop_table("ai_connections")
