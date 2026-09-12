"""ratings table — Database Schema V2 §1, API Specification V2 §4 (R.1-R.3).
Column set matches alembic/versions/0005_v2_ratings_replies_credits.py exactly.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_ratings_score"),
        UniqueConstraint("user_id", "post_id", name="ux_ratings_user_post"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id"), nullable=False)
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
