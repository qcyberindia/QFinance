"""ai_connections table — Database Schema delta (0006), BYOK.
`encrypted_api_key` holds Fernet ciphertext (see app/core/crypto.py), never
the raw key — renamed from an earlier, incorrect `api_key` (plaintext)
column; this migration was never applied to any real database (confirmed:
no execution access has existed in any session that touched this table), so
this is a direct correction, not a data migration. `encrypted_api_key` never
appears in any schema in ai/schemas.py, matching portfolio/models.py's
`access_token` precedent for "never returned via API," but going further
here since the DB column itself is now also non-reversible without the
configured secret.

PROVIDER REGISTRY (this pass): widened from a single hardcoded provider to
an explicit, small allow-list. "openai" is added because a real, already-
written adapter for it already exists (app/integrations/ai_providers/
openai_provider.py) — previously orphaned, wired to nothing (it belonged
only to the dead/unwired `modules/research_ai` module's own separate table).
No other provider (e.g. Gemini) is added, because no adapter code for one
exists anywhere in this repository — "only expose providers the existing
implementation can actually support" is taken literally, not aspirationally.
This still does not enable any live AI call: `modules/ai/service.py` has no
`.ask()`/call path today, only connect/status/disconnect — unchanged by
this pass. See alembic/versions/0008_ai_connections_add_openai_provider.py
for the corresponding CHECK-constraint migration.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

VALID_PROVIDERS = ("anthropic", "openai", "openai_compatible")
PROVIDER_OPENAI_COMPATIBLE = "openai_compatible"  # UI label: "OpenAI-Compatible" (not "Ollama" — provider-neutral)


class AIConnection(Base):
    __tablename__ = "ai_connections"
    __table_args__ = (
        CheckConstraint("provider IN ('anthropic', 'openai', 'openai_compatible')", name="ck_ai_connections_provider"),
        CheckConstraint(
            "provider <> 'openai_compatible' OR (endpoint IS NOT NULL AND model IS NOT NULL)",
            name="ck_ai_connections_compatible_fields",
        ),
        UniqueConstraint("user_id", "provider", name="ux_ai_connections_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="anthropic")
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet ciphertext; NEVER plaintext, NEVER returned via any API response
    # Only used by provider 'openai_compatible' (migration 0010). Neither is a secret:
    # endpoint is the normalized base URL (no credentials — rejected at input), model is
    # the user's chosen model id. Both are NULL for anthropic/openai rows.
    endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
