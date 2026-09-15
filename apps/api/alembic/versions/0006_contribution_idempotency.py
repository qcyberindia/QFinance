"""Add contributions.actor_id + a real uniqueness constraint for contribution
idempotency — Architecture V2 §7 (follow-up fix, does not touch 0005).

PROBLEM THIS FIXES: 0005's `contributions` table had no way to distinguish
WHO performed an engagement/rating from WHO receives the credit (`user_id`
is only the recipient). Without that, there was no correct database-level
way to prevent a single actor from farming credits by repeating an action
(e.g., unlike then re-like the same post) while still correctly allowing
MULTIPLE DIFFERENT actors to each independently earn credit for engaging
with the same piece of content, and still allowing the SAME actor to earn
credit for genuinely DISTINCT objects (e.g., two different comments).

FIX: add `actor_id` (who performed the action; for `thesis_published` this
equals `user_id`, since the actor and the beneficiary are the same person),
and a unique constraint on (actor_id, source_type, source_entity_id) — this
is the exact "(actor, event_type, target/object)" identity specified as the
correct dedup key, not "(event_type, target)" alone (which would have
wrongly prevented different actors from ever both earning credit for the
same post) and not "(actor, event_type)" alone (which would have wrongly
prevented the same actor from earning credit for two different objects).

`actor_id` is backfilled from `user_id` for any pre-existing rows (there are
none yet in practice — this table has not been written to by any code path
that reached a real database in this session — but the backfill is included
for correctness regardless of that).

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
