"""Community routes — API Specification V1 §4. Thin; delegates to service.py.

Route ordering: literal-prefixed routes (`/community/channels/...`,
`/community/posts/...`, `/community/comments/...`, `/community/bookmarks`)
are registered before the fully-dynamic `/community/{target_type}/{target_id}/reactions`
route, following the same static-before-dynamic discipline established in
research/router.py — even though in this specific route set no two routes
with the same HTTP method and segment count share an ambiguous literal/dynamic
first segment (verified by inspection before writing this file), registering
defensively avoids relying on that fact holding forever as routes are added.

Research-linked discussion endpoints (§4.1.5/§4.1.6) live under `/research/...`
per the locked API spec, not `/community/...` — a second router is defined
below and mounted at the `/research` prefix for exactly these two routes,
alongside the existing `research` module's own router (both mount under
`/research`, FastAPI supports multiple routers sharing a prefix).

WRITTEN, NOT EXECUTED."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_profile, get_current_user, require_csrf, require_role, require_verified_email, require_verified_profile
from app.core.errors import Forbidden
from app.modules.auth.models import User
from app.modules.community import service
from app.modules.community.schemas import (
    BookmarkCreateRequest, BookmarkCreateResponse, BookmarkListResponse, CommentCreateRequest, CommentListResponse,
    CommentPatchRequest, CommentResponse, PostCreateRequest, PostListResponse, PostPatchRequest, PostResponse,
    ReactionCreateRequest, ReactionCreateResponse,
)
from app.modules.research import service as research_service
from app.modules.users.models import Profile

router = APIRouter(prefix="/community", tags=["community"])
research_discussion_router = APIRouter(prefix="/research", tags=["community"])

_STAFF_ROLES = {"MODERATOR", "ADMIN", "SUPER_ADMIN"}


def _is_member(profile: Profile) -> bool:
    return "MEMBER" in profile.role_grants


def _is_staff(profile: Profile) -> bool:
    return bool(_STAFF_ROLES & set(profile.role_grants))


# ---------------------------------------------------------------------------
# 4.1 Posts and channels
# ---------------------------------------------------------------------------

@router.get("/channels/{channel}/posts", response_model=PostListResponse)
async def list_channel_posts(
    channel: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_moderated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
    user: User = Depends(get_current_user),
):
    """Basic/Pro product decision (see require_verified_profile's docstring):
    every channel, including non-announcements, is readable by any
    Authenticated + Verified user — the earlier `if not _is_member(profile):
    raise Forbidden('This channel requires Core membership.')` block is
    REMOVED. 'announcements' additionally never required Verified either
    (still true, preserved below) — the only remaining distinction between
    channels here is that non-announcements requires email verification,
    matching every other participation gate in this file.

    `include_moderated` (API Spec §10 end note / §12 item 3) is unaffected by
    this change — still passed through to service.list_channel_posts along
    with a server-computed `is_staff`, still only honored when both are true."""
    if channel != "announcements":
        if user.email_verified_at is None:
            raise Forbidden("Please verify your email address to continue.")
    items, total = await service.list_channel_posts(
        db, channel=channel, page=page, page_size=page_size,
        include_moderated=include_moderated, is_staff=_is_staff(profile),
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/channels/{channel}/posts", response_model=PostResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_channel_post(
    channel: str,
    body: PostCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """Basic/Pro product decision: posting no longer requires the old MEMBER
    ('Core membership') role_grant — only Authenticated + Verified
    (require_verified_profile). Announcements still additionally requires
    MODERATOR/ADMIN post rights (COMM-001) — that check is a moderation
    boundary, not a tier boundary, and is UNCHANGED."""
    if channel == "announcements" and not _is_staff(profile):
        raise Forbidden("Only MODERATOR/ADMIN may post to Announcements.")
    post = await service.create_channel_post(
        db, actor_id=profile.user_id, channel=channel, content=body.content, post_type=body.post_type,
    )
    serialized = await service.serialize_post(db, post)
    return serialized


@router.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
    user: User = Depends(get_current_user),
):
    """NEW this pass — genuinely absent before (confirmed: only list-by-channel
    and list-comments existed, no single-post fetch). Blocked the frontend
    post-detail page from ever showing the post's own content/author/
    post_type (needed for the Thesis Card) — only the comment thread was
    reachable. Same visibility gate as list_comments (which already needed
    to fetch the post via get_post_or_404 internally anyway, just never
    exposed it): non-announcements channels require Verified; Basic/Pro
    product decision applies identically to reading a single post as it
    does to listing them."""
    post = await service.get_post_or_404(db, post_id)
    if post.channel is not None and post.channel != "announcements":
        if user.email_verified_at is None:
            raise Forbidden("Please verify your email address to continue.")
    return await service.serialize_post(db, post)


@router.patch("/posts/{post_id}", response_model=PostResponse, dependencies=[Depends(require_csrf)])
async def patch_post(
    post_id: uuid.UUID,
    body: PostPatchRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    post = await service.patch_post(db, post_id=post_id, actor_id=profile.user_id, content=body.content)
    return await service.serialize_post(db, post)


@router.delete("/posts/{post_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_post(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.delete_post(db, post_id=post_id, actor_id=profile.user_id)


# ---------------------------------------------------------------------------
# 4.1.5/4.1.6 Research-linked discussion — mounted under /research
# ---------------------------------------------------------------------------

@research_discussion_router.get("/{research_id}/discussion", response_model=PostListResponse)
async def list_research_discussion(
    research_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
    _: User = Depends(require_verified_email),
):
    """Basic/Pro product decision: research discussions are readable by any
    Authenticated + Verified user, same as every other community surface —
    the earlier `if view.get("preview"): raise Forbidden('Research
    discussions require Core membership.')` block is REMOVED. Visibility of
    the underlying research item's actual CONTENT (core vs free_example
    access_tier) is unaffected by this change — that gate lives in
    research_service.get_research_view itself and still applies; this only
    removes the discussion-specific MEMBER overlay that previously sat on
    top of it."""
    await research_service.get_research_view(
        db, research_id, viewer_id=profile.user_id, viewer_is_member=_is_member(profile), is_staff=_is_staff(profile),
    )
    items, total = await service.list_research_discussion(db, research_id=research_id, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@research_discussion_router.post("/{research_id}/discussion", response_model=PostResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_research_discussion_post(
    research_id: uuid.UUID,
    body: PostCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    # Confirms the research item exists and is visible before allowing discussion on it.
    await research_service.get_research_view(
        db, research_id, viewer_id=profile.user_id, viewer_is_member=True, is_staff=_is_staff(profile),
    )
    post = await service.create_research_discussion_post(
        db, actor_id=profile.user_id, research_id=research_id, content=body.content,
    )
    return await service.serialize_post(db, post)


# ---------------------------------------------------------------------------
# 4.2 Comments
# ---------------------------------------------------------------------------

@router.get("/posts/{post_id}/comments", response_model=CommentListResponse)
async def list_comments(
    post_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_moderated: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
    user: User = Depends(get_current_user),
):
    """§4.2.1 — 'Same visibility as the parent post' is enforced in two layers,
    matching what 'visibility' actually means for a post per §4.1.1/§4.1.6:
    (1) moderation-status visibility (visible/restricted/removed) — delegated to
        service.list_comments, including the staff-only `include_moderated`
        override (server-computed `is_staff`, never trusted from the raw
        query string alone — identical gating discipline as list_channel_posts
        above and research's list_library/search_research).
    (2) channel/research-discussion AUTH-TIER visibility — the gate that decides
        whether the caller could even list this post in the first place. This was
        MISSING before an earlier fix: a caller who is Authenticated but not Verified/
        MEMBER could previously read comments on a post in a Verified+MEMBER-gated
        channel (or a MEMBER-gated research discussion) directly via this endpoint,
        bypassing the same gate §4.1.1/§4.1.6 enforce on the post itself. Fixed by
        checking the SAME two conditions those endpoints check, applied to this
        comment's parent post, before calling into service.list_comments at all.
        `include_moderated` cannot bypass this layer either — it is only consulted
        after this auth-tier gate passes.
    """
    post = await service.get_post_or_404(db, post_id)
    if post.channel is not None and post.channel != "announcements":
        if user.email_verified_at is None:
            raise Forbidden("Please verify your email address to continue.")
    # Basic/Pro product decision: the prior MEMBER-only gates for
    # non-announcements channels and research-linked discussions are REMOVED
    # here too, matching the parent post's own (now-Basic-accessible) read gate.

    items, total = await service.list_comments(
        db, post_id=post_id, viewer_id=profile.user_id, is_staff=_is_staff(profile), page=page, page_size=page_size,
        include_moderated=include_moderated,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/posts/{post_id}/comments", response_model=CommentResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_comment(
    post_id: uuid.UUID,
    body: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    comment = await service.create_comment(db, actor_id=profile.user_id, post_id=post_id, content=body.content)
    return await service.serialize_comment(db, comment)


@router.patch("/comments/{comment_id}", response_model=CommentResponse, dependencies=[Depends(require_csrf)])
async def patch_comment(
    comment_id: uuid.UUID,
    body: CommentPatchRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    comment = await service.patch_comment(db, comment_id=comment_id, actor_id=profile.user_id, content=body.content)
    return await service.serialize_comment(db, comment)


@router.delete("/comments/{comment_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_comment(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
):
    await service.delete_comment(db, comment_id=comment_id, actor_id=profile.user_id)


@router.post("/comments/{comment_id}/replies", response_model=CommentResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_reply(
    comment_id: uuid.UUID,
    body: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    """V2 API Spec §3 — same auth (MEMBER) as top-level comment creation;
    ownership/visibility of the parent comment+post is checked inside
    service.create_reply. Registered here, alongside
    /posts/{post_id}/comments, before the fully-dynamic reactions route
    below (same static-before-dynamic discipline as the rest of this file).
    """
    reply = await service.create_reply(db, actor_id=profile.user_id, comment_id=comment_id, content=body.content)
    return await service.serialize_comment(db, reply)


# ---------------------------------------------------------------------------
# 4.4 Bookmarks — registered before the fully-dynamic reactions route below
# ---------------------------------------------------------------------------

@router.post("/bookmarks", response_model=BookmarkCreateResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def add_bookmark(
    body: BookmarkCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    bookmark = await service.add_bookmark(db, actor_id=profile.user_id, post_id=uuid.UUID(body.post_id))
    return BookmarkCreateResponse(id=str(bookmark.id))


@router.delete("/bookmarks/{post_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_bookmark(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    await service.remove_bookmark(db, actor_id=profile.user_id, post_id=post_id)


@router.get("/bookmarks", response_model=BookmarkListResponse)
async def list_bookmarks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    items, total = await service.list_bookmarks(db, actor_id=profile.user_id, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


# ---------------------------------------------------------------------------
# 4.3 Reactions — fully-dynamic route, registered LAST
# ---------------------------------------------------------------------------

@router.post("/{target_type}/{target_id}/reactions", response_model=ReactionCreateResponse, status_code=201,
             dependencies=[Depends(require_csrf)])
async def add_reaction(
    target_type: str,
    target_id: uuid.UUID,
    body: ReactionCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    reaction = await service.add_reaction(
        db, actor_id=profile.user_id, target_type=target_type, target_id=target_id, reaction_type=body.reaction_type,
    )
    return ReactionCreateResponse(id=str(reaction.id))


@router.delete("/{target_type}/{target_id}/reactions", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_reaction(
    target_type: str,
    target_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_verified_profile),
):
    await service.remove_reaction(db, actor_id=profile.user_id, target_type=target_type, target_id=target_id)
