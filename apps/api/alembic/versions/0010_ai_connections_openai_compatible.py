"""ai_connections: add the OpenAI-Compatible provider.

Additive: two nullable columns (`endpoint`, `model`) and a widened provider
CHECK. No existing row is touched; existing 'anthropic'/'openai' rows keep
NULL endpoint/model. A second CHECK guarantees an `openai_compatible` row can
never exist without both an endpoint and a model, so the row is always usable
by the provider adapter.

The API key is NOT a new column: it continues to live only in the existing
`encrypted_api_key` (Fernet ciphertext).

downgrade() recreates the narrower provider CHECK BEFORE dropping the
columns; if any `openai_compatible` row exists it fails loudly (transactional
DDL rolls back) rather than silently deleting a user's saved connection.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_connections", sa.Column("endpoint", sa.Text(), nullable=True))
    op.add_column("ai_connections", sa.Column("model", sa.Text(), nullable=True))
    op.drop_constraint("ck_ai_connections_provider", "ai_connections", type_="check")
    op.create_check_constraint(
        "ck_ai_connections_provider", "ai_connections",
        "provider IN ('anthropic', 'openai', 'openai_compatible')",
    )
    op.create_check_constraint(
        "ck_ai_connections_compatible_fields", "ai_connections",
        "provider <> 'openai_compatible' OR (endpoint IS NOT NULL AND model IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_connections_compatible_fields", "ai_connections", type_="check")
    op.drop_constraint("ck_ai_connections_provider", "ai_connections", type_="check")
    op.create_check_constraint(
        "ck_ai_connections_provider", "ai_connections", "provider IN ('anthropic', 'openai')",
    )
    op.drop_column("ai_connections", "model")
    op.drop_column("ai_connections", "endpoint")
