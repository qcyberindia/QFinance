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
from app.core.deps import get_current_profile, get_current_user, require_csrf, require_role, require_verified_email
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
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
    user: User = Depends(get_current_user),
):
    """§4.1.1 — exact auth tier per endpoint, not a blanket rule: any
    Authenticated caller (regardless of email-verification status) may GET
    'announcements'; every other channel requires Authenticated + Verified
    (checked here, since Verified is conditional on the channel and can't be
    expressed as a single unconditional Depends) AND MEMBER."""
    if channel != "announcements":
        if user.email_verified_at is None:
            raise Forbidden("Please verify your email address to continue.")
        if not _is_member(profile):
            raise Forbidden("This channel requires Core membership.")
    items, total = await service.list_channel_posts(db, channel=channel, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/channels/{channel}/posts", response_model=PostResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_channel_post(
    channel: str,
    body: PostCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
):
    """§4.1.2 — Announcements additionally requires MODERATOR/ADMIN post rights (COMM-001)."""
    if channel == "announcements" and not _is_staff(profile):
        raise Forbidden("Only MODERATOR/ADMIN may post to Announcements.")
    post = await service.create_channel_post(db, actor_id=profile.user_id, channel=channel, content=body.content)
    serialized = await service.serialize_post(db, post)
    return serialized


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
    """§4.1.5 — Authenticated + Verified (unconditional here, unlike §4.1.1's
    announcements exception), plus 'tier rules per LIB-003': a caller who
    cannot see the research item's full content (i.e. gets a preview, not the
    full representation) cannot see its discussion either, since MEM-003
    lists 'research discussions' as Core-gated in its own right, not merely
    inherited from the research item's own tier gate."""
    view = await research_service.get_research_view(
        db, research_id, viewer_id=profile.user_id, viewer_is_member=_is_member(profile), is_staff=_is_staff(profile),
    )
    if view.get("preview"):
        raise Forbidden("Research discussions require Core membership.")
    items, total = await service.list_research_discussion(db, research_id=research_id, page=page, page_size=page_size)
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@research_discussion_router.post("/{research_id}/discussion", response_model=PostResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_research_discussion_post(
    research_id: uuid.UUID,
    body: PostCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
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
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(get_current_profile),
    user: User = Depends(get_current_user),
):
    """§4.2.1 — 'Same visibility as the parent post' is enforced in two layers,
    matching what 'visibility' actually means for a post per §4.1.1/§4.1.6:
    (1) moderation-status visibility (visible/restricted/removed) — delegated to
        service.list_comments, unchanged.
    (2) channel/research-discussion AUTH-TIER visibility — the gate that decides
        whether the caller could even list this post in the first place. This was
        MISSING before this fix: a caller who is Authenticated but not Verified/
        MEMBER could previously read comments on a post in a Verified+MEMBER-gated
        channel (or a MEMBER-gated research discussion) directly via this endpoint,
        bypassing the same gate §4.1.1/§4.1.6 enforce on the post itself. Fixed by
        checking the SAME two conditions those endpoints check, applied to this
        comment's parent post, before calling into service.list_comments at all.
    """
    post = await service.get_post_or_404(db, post_id)
    if post.channel is not None and post.channel != "announcements":
        if user.email_verified_at is None:
            raise Forbidden("Please verify your email address to continue.")
        if not _is_member(profile):
            raise Forbidden("This channel requires Core membership.")
    # post.channel is None => a research-linked post (§4.1.6) — §4.2.1 inherits
    # the same requires-MEMBER gate §4.1.6 applies to posting in that discussion,
    # since MEM-003 lists "research discussions" as Core-gated in their own
    # right (see the FLAGGED, UNRESOLVED spec question in work_memory.md about
    # §4.1.5's narrower reading of this same rule — this comments-read path
    # is NOT ambiguous the same way, because §4.2.1's "same as parent post"
    # wording directly ties it to whatever gate governs the post, and §4.1.6
    # unambiguously requires MEMBER for research-linked posts).
    elif post.channel is None and post.research_id is not None:
        if not _is_member(profile):
            raise Forbidden("This discussion requires Core membership.")

    items, total = await service.list_comments(
        db, post_id=post_id, viewer_id=profile.user_id, is_staff=_is_staff(profile), page=page, page_size=page_size,
    )
    return {"items": items, "page": page, "page_size": page_size, "total": total}


@router.post("/posts/{post_id}/comments", response_model=CommentResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def create_comment(
    post_id: uuid.UUID,
    body: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
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


# ---------------------------------------------------------------------------
# 4.4 Bookmarks — registered before the fully-dynamic reactions route below
# ---------------------------------------------------------------------------

@router.post("/bookmarks", response_model=BookmarkCreateResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def add_bookmark(
    body: BookmarkCreateRequest,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
):
    bookmark = await service.add_bookmark(db, actor_id=profile.user_id, post_id=uuid.UUID(body.post_id))
    return BookmarkCreateResponse(id=str(bookmark.id))


@router.delete("/bookmarks/{post_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def remove_bookmark(
    post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
):
    await service.remove_bookmark(db, actor_id=profile.user_id, post_id=post_id)


@router.get("/bookmarks", response_model=BookmarkListResponse)
async def list_bookmarks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    profile: Profile = Depends(require_role("MEMBER")),
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
    profile: Profile = Depends(require_role("MEMBER")),
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
    profile: Profile = Depends(require_role("MEMBER")),
):
    await service.remove_reaction(db, actor_id=profile.user_id, target_type=target_type, target_id=target_id)
