from datetime import datetime

from pydantic import BaseModel

from app.modules.community.models import CHANNELS


class PostCreateRequest(BaseModel):
    content: str
    post_type: str = "general"  # V2 API Spec §3 — default preserves V1 request shape


class PostPatchRequest(BaseModel):
    content: str


class AuthorRef(BaseModel):
    id: str
    name: str | None = None
    username: str | None = None


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


class BookmarkListResponse(BaseModel):
    items: list[BookmarkItem]
    page: int
    page_size: int
    total: int
