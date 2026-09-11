"""Portfolio module models — Database Schema V2 §1 `broker_connections`.
WRITTEN, NOT EXECUTED.

`access_token` is application-layer-encrypted-at-rest is a recommended
hardening NOT implemented in MVP — flagged explicitly in the locked schema
doc and restated here rather than silently omitted. This column is never
serialized into any API response anywhere in this module (see schemas.py —
no response schema includes it at all, not even as an optional/masked field).
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

VALID_BROKERS = ("zerodha",)
VALID_CONNECTION_STATUSES = ("connected", "disconnected", "error")


class BrokerConnection(Base):
    __tablename__ = "broker_connections"
    __table_args__ = (
        CheckConstraint("broker = 'zerodha'", name="ck_broker_connections_broker"),
        CheckConstraint("status IN ('connected','disconnected','error')", name="ck_broker_connections_status"),
        UniqueConstraint("user_id", "broker", name="ux_broker_connections_user_broker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    broker: Mapped[str] = mapped_column(Text, nullable=False, default="zerodha")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # NEVER returned via any API response
    kite_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
