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
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

VALID_PROVIDERS = ("anthropic",)


class AIConnection(Base):
    __tablename__ = "ai_connections"
    __table_args__ = (
        CheckConstraint("provider = 'anthropic'", name="ck_ai_connections_provider"),
        UniqueConstraint("user_id", "provider", name="ux_ai_connections_user_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, default="anthropic")
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet ciphertext; NEVER plaintext, NEVER returned via any API response
    connected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
