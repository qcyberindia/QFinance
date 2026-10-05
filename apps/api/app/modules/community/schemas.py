from datetime import datetime

from pydantic import BaseModel

from app.modules.community.models import CHANNELS


class PostCreateRequest(BaseModel):
    content: str
    post_type: str = "general"  # V2 API Spec §3 — default preserves V1 request shape


class PostPatchRequest(BaseModel):
    content: str


class AuthorRef(BaseModel):
    """SECURITY FIX (this pass): `name` removed — previously exposed the
    real registration name on every post/comment author. `username` is the
    only public, pseudonymous identity attached to community content."""
    id: str
    username: str | None = None


class ThesisCompanyRef(BaseModel):
    name: str | None = None
    symbol: str | None = None
    exchange: str | None = None


class ThesisRef(BaseModel):
    """Public reference to a thesis post's published research (title,
    company, version) — present only while that research is published."""
    research_title: str | None = None
    version: int
    published_at: datetime | None = None
    company: ThesisCompanyRef


class PostResponse(BaseModel):
    id: str
    channel: str | None
    research_id: str | None
    post_type: str
    author: AuthorRef
    content: str
    created_at: datetime
    updated_at: datetime
    is_edited: bool
    status: str
    reaction_count: int
    comment_count: int
    viewer_reacted: bool = False
    viewer_bookmarked: bool = False
    thesis: ThesisRef | None = None


class ThesisSource(BaseModel):
    label: str | None = None
    reference: str | None = None
    supports_claim: str | None = None


class ThesisSnapshotResponse(BaseModel):
    """The published reasoning behind a thesis post, from the latest
    immutable research_versions snapshot (community/service.py's
    THESIS_SNAPSHOT_FIELDS allow-list)."""
    post_id: str
    company: ThesisCompanyRef
    version: int
    version_created_at: datetime
    published_at: datetime | None = None
    sections: dict[str, str | bool | None]
    sources: list[ThesisSource]


class PostListResponse(BaseModel):
    items: list[PostResponse]
    page: int
    page_size: int
    total: int


class CommentCreateRequest(BaseModel):
    content: str


class CommentPatchRequest(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: str
    post_id: str
    parent_comment_id: str | None
    author: AuthorRef
    content: str
    created_at: datetime
    is_edited: bool
    status: str


class CommentListResponse(BaseModel):
    items: list[CommentResponse]
    page: int
    page_size: int
    total: int


class ReactionCreateRequest(BaseModel):
    reaction_type: str = "like"


class ReactionCreateResponse(BaseModel):
    id: str


class BookmarkCreateRequest(BaseModel):
    post_id: str


class BookmarkCreateResponse(BaseModel):
    id: str


class BookmarkItem(BaseModel):
    post_id: str
    post_summary: str
    bookmarked_at: datetime
    post_type: str | None = None  # None when the post is no longer available
    available: bool = True


class BookmarkListResponse(BaseModel):
    items: list[BookmarkItem]
    page: int
    page_size: int
    total: int
