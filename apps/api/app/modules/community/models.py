"""posts / comments / reactions / bookmarks — Architecture §4.2/§5.3, Database
Schema V1 §12-14/§17 + V2 §2 (post_type, parent_comment_id). Column set matches
alembic/versions/0001_initial_schema.py + 0005_v2_ratings_replies_credits.py
exactly — no columns invented here that aren't in a migration.
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.db import Base

CHANNELS = (
    "announcements", "general_discussion", "research_discussion",
    "market_discussion", "learning", "help_questions", "off_topic",
)

POST_TYPES = ("general", "thesis", "question", "discussion")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            "channel IS NULL OR channel IN "
            "('announcements','general_discussion','research_discussion','market_discussion',"
            "'learning','help_questions','off_topic')",
            name="ck_posts_channel",
        ),
        CheckConstraint("channel IS NOT NULL OR research_id IS NOT NULL", name="ck_posts_channel_or_research"),
        CheckConstraint("status IN ('visible','restricted','removed')", name="ck_posts_status"),
        CheckConstraint("post_type IN ('general','thesis','question','discussion')", name="ck_posts_post_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("research.id"), nullable=True)
    post_type: Mapped[str] = mapped_column(Text, nullable=False, default="general")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="visible")
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint("status IN ('visible','restricted','removed')", name="ck_comments_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("comments.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="visible")
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        CheckConstraint("target_type IN ('post','comment')", name="ck_reactions_target_type"),
        CheckConstraint("reaction_type = 'like'", name="ck_reactions_type"),
        UniqueConstraint("user_id", "target_type", "target_id", "reaction_type", name="ux_reactions_unique"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reaction_type: Mapped[str] = mapped_column(Text, nullable=False, default="like")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)


class Bookmark(Base):
    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="ux_bookmarks_user_post"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    post_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("posts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
