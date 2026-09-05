"""events table — Architecture §21/AD-15 (ANLY-001-003, OD-09). Append-only.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

_EVENT_TYPES = (
    "signup", "email_verified", "login", "payment_completed",
    "research_draft_created", "research_draft_updated", "research_section_completed",
    "research_source_added", "research_published", "research_commented",
    "post_created", "watchlist_added",
)


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(f"event_type IN {_EVENT_TYPES}", name="ck_events_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


async def emit_event(db, *, user_id, event_type: str, entity_type: str | None = None,
                      entity_id=None, metadata: dict | None = None) -> None:
    """Written from service layer only, in the same transaction as the triggering
    write (Architecture §21.2/21.13/21.14) — never from routes, never from the frontend."""
    db.add(Event(user_id=user_id, event_type=event_type, entity_type=entity_type,
                  entity_id=entity_id, metadata_=metadata))
