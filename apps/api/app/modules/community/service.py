"""Community business logic — API Specification V1 §4 (COMM-*, PCR-*, OD-14).
WRITTEN, NOT EXECUTED — no real database has been reached in this session.

CROSS-MODULE DEPENDENCY FLAGGED, NOT SILENTLY WORKED AROUND: API Spec §4.1.2/
§4.2.2 both reference flagged-phrase matching against `moderation_rules`
(MOD-003) creating "an auto-generated reports-queue-equivalent entry." The
`moderation_rules` table already exists (alembic/versions/0001_initial_schema.py),
so the phrase list itself is readable here — but `reports.reporter_id` is
`NOT NULL` (Database Schema §15) and no "system actor" concept exists anywhere
in this codebase. Rather than (a) adding a nullable-reporter schema change to
an already-approved table without founder sign-off, or (b) silently skipping
MOD-003 for Community and pretending the requirement is satisfied, this
module attributes an auto-flagged report's `reporter_id` to the flagged
content's own author — mirroring the exact precedent already established for
self-delete audit trails elsewhere in this codebase (distinguishing
self-initiated from moderator-initiated action by *who* the actor is, not by
inventing a new nullable actor concept) — and marks the `reason` text with an
unambiguous "Automated flag:" prefix so it is never confused with a genuine
member complaint when the Moderation module's queue view (§5.2, next module)
reads from the same `reports` table. This is a real design decision, not a
bug fix, and is recorded in work_memory.md.

COMM-007 (member-submitted reports) is intentionally NOT implemented here —
API Spec §5.1 `POST /moderation/reports` is a `moderation` module endpoint,
not a `community` one; building it now would be scope creep into the next
module. This means COMM-007's acceptance criterion is not independently
satisfiable until `moderation` ships — flagged explicitly in work_memory.md,
not hidden.
"""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import Forbidden, NotFound, QFinanceAPIError
from app.modules.analytics.models import emit_event
from app.modules.community.models import CHANNELS, POST_TYPES, Bookmark, Comment, Post, Reaction
from app.modules.users import service as users_service

VALID_TARGET_TYPES = ("post", "comment")


async def _load_author(db: AsyncSession, author_id: uuid.UUID) -> dict:
    """SECURITY FIX (this pass): previously also selected and returned
    `profiles.name` (the real registration name) for every post/comment
    author, alongside `username` — the identical real-identity leak already
    found and fixed in profile/service.py's public endpoint, just not yet
    applied here. The core loop's 'PSEUDONYMOUS COMMUNITY IDENTITY' step
    requires `username` to be the only public identity attached to any
    community content; `name` is no longer selected from the database at
    all in this query, so there is no real-name value in scope to leak
    even if a future change to the return dict got careless."""
    row = (await db.execute(
        text("SELECT user_id, username FROM profiles WHERE user_id = :uid"), {"uid": str(author_id)},
    )).first()
    return ({"id": str(row.user_id), "username": row.username} if row
            else {"id": str(author_id), "username": None})


async def _match_flagged_phrases(db: AsyncSession, content: str) -> list[str]:
    """MOD-003 — read-only lookup against `moderation_rules` (owned by the
    not-yet-built `moderation` module; read via raw SQL rather than an ORM
    cross-import, matching the pattern already used elsewhere in this
    codebase — e.g. companies/service.py's cross-module read of research/posts
    counts). Case-insensitive substring match; MVP does not need anything
    more sophisticated per MOD-003's own wording ("phrases ... stored in an
    admin-configurable table")."""
    rows = (await db.execute(
        text("SELECT phrase FROM moderation_rules WHERE enabled = true")
    )).all()
    content_lower = content.lower()
    return [row.phrase for row in rows if row.phrase.lower() in content_lower]


async def _auto_flag_if_needed(db: AsyncSession, *, target_type: str, target_id: uuid.UUID,
                                author_id: uuid.UUID, content: str) -> None:
    matches = await _match_flagged_phrases(db, content)
    if not matches:
        return
    # See module docstring for the reporter_id=author_id design decision.
    await db.execute(
        text(
            "INSERT INTO reports (id, reporter_id, target_type, target_id, reason, status) "
            "VALUES (:id, :reporter_id, :target_type, :target_id, :reason, 'open')"
        ),
        {
            "id": str(uuid.uuid4()), "reporter_id": str(author_id), "target_type": target_type,
            "target_id": str(target_id),
            "reason": f"Automated flag: matched moderation_rules phrase(s): {', '.join(matches)}",
        },
    )


# ---------------------------------------------------------------------------
# Posts — channels
# ---------------------------------------------------------------------------

def validate_channel(channel: str) -> None:
    if channel not in CHANNELS:
        raise QFinanceAPIError("INVALID_CHANNEL", f"channel must be one of {CHANNELS}.", 400)


def validate_post_type(post_type: str) -> None:
    """V2 API Spec §3 — defaults to 'general' at the schema layer, but an
    explicitly-invalid value must still be rejected rather than silently
    coerced, matching every other enum-like validator in this codebase."""
    if post_type not in POST_TYPES:
        raise QFinanceAPIError("INVALID_POST_TYPE", f"post_type must be one of {POST_TYPES}.", 400)


async def _post_counts(db: AsyncSession, post_id: uuid.UUID) -> tuple[int, int]:
    reaction_count = (await db.execute(
        text("SELECT COUNT(*) FROM reactions WHERE target_type = 'post' AND target_id = :pid"),
        {"pid": str(post_id)},
    )).scalar_one()
    comment_count = (await db.execute(
        text("SELECT COUNT(*) FROM comments WHERE post_id = :pid AND status != 'removed'"),
        {"pid": str(post_id)},
    )).scalar_one()
    return reaction_count, comment_count


async def _thesis_ref(db: AsyncSession, research_id: uuid.UUID) -> dict | None:
    """Small public reference for a thesis post's linked research — only
    when that research is currently published and not moderated. Company
    data is public/static; no author or draft fields are read here."""
    row = (await db.execute(
        text(
            "SELECT r.title, r.status, r.moderation_status, r.current_version, r.published_at, "
            "c.name AS company_name, c.symbol AS company_symbol, c.exchange AS company_exchange "
            "FROM research r LEFT JOIN companies c ON c.id = r.company_id WHERE r.id = :rid"
        ),
        {"rid": str(research_id)},
    )).first()
    if row is None or row.status != "published" or row.moderation_status != "active":
        return None
    return {
        "research_title": row.title, "version": row.current_version, "published_at": row.published_at,
        "company": {"name": row.company_name, "symbol": row.company_symbol, "exchange": row.company_exchange},
    }


async def _viewer_flags(db: AsyncSession, post_id: uuid.UUID, viewer_id: uuid.UUID | None) -> tuple[bool, bool]:
    if viewer_id is None:
        return False, False
    reacted = (await db.execute(
        text("SELECT 1 FROM reactions WHERE target_type = 'post' AND target_id = :pid AND user_id = :uid LIMIT 1"),
        {"pid": str(post_id), "uid": str(viewer_id)},
    )).first() is not None
    bookmarked = (await db.execute(
        text("SELECT 1 FROM bookmarks WHERE post_id = :pid AND user_id = :uid LIMIT 1"),
        {"pid": str(post_id), "uid": str(viewer_id)},
    )).first() is not None
    return reacted, bookmarked


async def serialize_post(db: AsyncSession, post: Post, *, viewer_id: uuid.UUID | None = None) -> dict:
    author = await _load_author(db, post.author_id)
    reaction_count, comment_count = await _post_counts(db, post.id)
    viewer_reacted, viewer_bookmarked = await _viewer_flags(db, post.id, viewer_id)
    thesis = await _thesis_ref(db, post.research_id) if post.post_type == "thesis" and post.research_id else None
    return {
        "id": str(post.id), "channel": post.channel, "research_id": str(post.research_id) if post.research_id else None,
        "post_type": post.post_type, "author": author, "content": post.content,
        "created_at": post.created_at, "updated_at": post.updated_at,
        "is_edited": post.is_edited, "status": post.status,
        "reaction_count": reaction_count, "comment_count": comment_count,
        "viewer_reacted": viewer_reacted, "viewer_bookmarked": viewer_bookmarked,
        "thesis": thesis,
    }


# Community pillars -> post_type values. 'general' is the legacy default
# type and reads as a discussion.
PILLAR_POST_TYPES = {
    "discussion": ("general", "discussion"),
    "question": ("question",),
    "thesis": ("thesis",),
}


async def list_feed(db: AsyncSession, *, pillar: str | None, page: int, page_size: int,
                    viewer_id: uuid.UUID | None) -> tuple[list[dict], int]:
    """One feed across the Community pillars. Channel posts (except
    staff-only announcements) plus thesis posts, which live on
    `posts.research_id` with `channel=NULL` (Architecture V2 §5) and so are
    unreachable through any channel listing. Plain research-discussion posts
    (research-linked, not thesis) stay on their research item, not the feed.
    Visible posts only."""
    if pillar is not None and pillar not in PILLAR_POST_TYPES:
        raise QFinanceAPIError("INVALID_PILLAR", f"pillar must be one of {tuple(PILLAR_POST_TYPES)}.", 400)
    conditions = [
        Post.status == "visible",
        or_(and_(Post.channel.is_not(None), Post.channel != "announcements"), Post.post_type == "thesis"),
    ]
    if pillar is not None:
        conditions.append(Post.post_type.in_(PILLAR_POST_TYPES[pillar]))
    total = (await db.execute(select(func.count()).select_from(Post).where(*conditions))).scalar_one()
    rows = (await db.execute(
        select(Post).where(*conditions)
        .order_by(Post.created_at.desc(), Post.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return [await serialize_post(db, p, viewer_id=viewer_id) for p in rows], total


# Published-snapshot fields a thesis post may show. An explicit allow-list:
# anything not named here (including fields added to snapshots later) is
# never exposed through Community.
THESIS_SNAPSHOT_FIELDS = (
    "title", "summary", "business_model", "business_quality", "competitive_position", "financial_snapshot",
    "catalysts", "management_notes", "assumptions_outlook", "valuation_range",
    "bull_case", "base_case", "bear_case", "risk_register", "invalidation_conditions",
    "conflict_disclosed", "conflict_detail", "position_disclosed", "position_detail", "research_date",
)


async def get_thesis_snapshot(db: AsyncSession, *, post: Post) -> dict:
    """The published reasoning behind a thesis post, read from the latest
    immutable `research_versions` snapshot (written on every publish and
    post-publish edit) — never from the live row, so unpublished draft text
    can't reach Community."""
    if post.post_type != "thesis" or post.research_id is None:
        raise NotFound("This post has no linked thesis.")
    ref = await _thesis_ref(db, post.research_id)
    if ref is None:
        raise NotFound("This thesis is no longer available.")
    row = (await db.execute(
        text(
            "SELECT version_number, snapshot, created_at FROM research_versions "
            "WHERE research_id = :rid ORDER BY version_number DESC LIMIT 1"
        ),
        {"rid": str(post.research_id)},
    )).first()
    if row is None:
        raise NotFound("This thesis is no longer available.")
    snap = row.snapshot or {}
    sections = {f: snap.get(f) for f in THESIS_SNAPSHOT_FIELDS}
    sources = [
        {"label": s.get("label"), "reference": s.get("reference"), "supports_claim": s.get("supports_claim")}
        for s in (snap.get("sources") or [])
    ]
    return {
        "post_id": str(post.id), "company": ref["company"], "version": row.version_number,
        "version_created_at": row.created_at, "published_at": ref["published_at"],
        "sections": sections, "sources": sources,
    }


async def list_channel_posts(db: AsyncSession, *, channel: str, page: int, page_size: int,
                              include_moderated: bool = False, is_staff: bool = False) -> tuple[list[dict], int]:
    """§4.1.1. `include_moderated` (API Spec §10 end note / §12 item 3) is a staff-only
    override, matching the exact pattern already established in
    research/service.py's list_library/search_research: the effective flag is
    `include_moderated and is_staff`, computed here (not trusted from a raw
    client query-string value alone) so an ordinary member passing
    `?include_moderated=true` gets the unchanged default ('visible' only).
    Default behavior (no flag, or non-staff caller) is unchanged from before
    this fix."""
    validate_channel(channel)
    effective_include_moderated = include_moderated and is_staff
    statuses = ("visible", "restricted", "removed") if effective_include_moderated else ("visible",)

    total = (await db.execute(
        select(func.count()).select_from(Post).where(Post.channel == channel, Post.status.in_(statuses))
    )).scalar_one()
    rows = (await db.execute(
        select(Post).where(Post.channel == channel, Post.status.in_(statuses))
        .order_by(Post.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return [await serialize_post(db, p) for p in rows], total


async def create_channel_post(db: AsyncSession, *, actor_id: uuid.UUID, channel: str, content: str,
                               post_type: str = "general") -> Post:
    """§4.1.2 + V2 API Spec §3's `post_type` addition. CMPL-004 first-post gate
    + MOD-003 flagged-phrase signal, both unchanged from V1."""
    validate_channel(channel)
    validate_post_type(post_type)
    if post_type == "thesis":
        # A thesis is published from Research (POST /research/{id}/publish-to-community),
        # which links it to the author's published, versioned reasoning.
        raise QFinanceAPIError(
            "THESIS_REQUIRES_RESEARCH", "Publish a thesis from your Research instead of posting it directly.", 400,
        )
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Post content cannot be empty.", 400, fields={"content": "required"})

    if not await users_service.has_acknowledged_current_charter(db, user_id=actor_id):
        raise QFinanceAPIError(
            "CHARTER_NOT_ACKNOWLEDGED",
            "You must acknowledge the Member Charter before posting.", 403,
        )

    post = Post(id=uuid.uuid4(), author_id=actor_id, channel=channel, research_id=None,
                post_type=post_type, content=content, status="visible")
    db.add(post)
    await db.flush()

    await _auto_flag_if_needed(db, target_type="post", target_id=post.id, author_id=actor_id, content=content)
    await emit_event(db, user_id=actor_id, event_type="post_created", entity_type="post", entity_id=post.id)
    await db.commit()
    return post


async def get_post_or_404(db: AsyncSession, post_id: uuid.UUID) -> Post:
    post = await db.get(Post, post_id)
    if post is None:
        raise NotFound("Post not found.")
    return post


def _visible_to(post_or_comment, *, viewer_id: uuid.UUID | None, is_staff: bool) -> bool:
    """§10.1 moderation-status semantics: visible=all, restricted=author+staff, removed=nobody (incl. author)."""
    if post_or_comment.status == "visible":
        return True
    if post_or_comment.status == "restricted":
        return is_staff or post_or_comment.author_id == viewer_id
    return False  # removed — hidden from everyone including the author


def _require_author(item, actor_id: uuid.UUID) -> None:
    if item.author_id != actor_id:
        raise Forbidden("Only the author may modify this content.")


VALID_CONTENT_STATUSES = ("visible", "restricted", "removed")


async def apply_moderation_status_to_post(db: AsyncSession, *, post_id: uuid.UUID, new_status: str) -> str:
    """Used by moderation/service.py's take_action (API Spec §5.3) as one leg of
    a single, atomic, multi-table transaction (target status + moderation_actions
    + reports + audit_logs, all-or-nothing per Architecture §10.1). Deliberately
    does NOT call db.commit() — unlike every other function in this file — so the
    caller controls the transaction boundary. This is a narrow, documented
    exception to this module's usual per-function-commits-its-own-work style,
    made necessary because no unit-of-work/uncommitted-session pattern exists
    elsewhere in this codebase; the alternative (moderation reaching directly
    into `posts`/`comments` ORM models or raw SQL) would duplicate this
    module's own status-semantics knowledge instead of reusing it. Returns the
    previous status so the caller can record it in `moderation_actions`/
    `audit_logs` without a second query."""
    if new_status not in VALID_CONTENT_STATUSES:
        raise QFinanceAPIError("INVALID_MODERATION_STATUS", f"status must be one of {VALID_CONTENT_STATUSES}.", 400)
    post = await get_post_or_404(db, post_id)
    previous_state = post.status
    post.status = new_status
    await db.flush()
    return previous_state


async def apply_moderation_status_to_comment(db: AsyncSession, *, comment_id: uuid.UUID, new_status: str) -> str:
    """See apply_moderation_status_to_post's docstring — identical contract for comments."""
    if new_status not in VALID_CONTENT_STATUSES:
        raise QFinanceAPIError("INVALID_MODERATION_STATUS", f"status must be one of {VALID_CONTENT_STATUSES}.", 400)
    comment = await get_comment_or_404(db, comment_id)
    previous_state = comment.status
    comment.status = new_status
    await db.flush()
    return previous_state


async def apply_moderator_edit_to_post(db: AsyncSession, *, post_id: uuid.UUID, new_content: str) -> str:
    """MOD-002 'Edit' action (§5.3) — same non-committing contract as the status
    functions above. Returns the previous content (for audit before_state)."""
    post = await get_post_or_404(db, post_id)
    previous_content = post.content
    post.content = new_content
    post.is_edited = True
    await db.flush()
    return previous_content


async def apply_moderator_edit_to_comment(db: AsyncSession, *, comment_id: uuid.UUID, new_content: str) -> str:
    comment = await get_comment_or_404(db, comment_id)
    previous_content = comment.content
    comment.content = new_content
    comment.is_edited = True
    await db.flush()
    return previous_content


async def patch_post(db: AsyncSession, *, post_id: uuid.UUID, actor_id: uuid.UUID, content: str) -> Post:
    """§4.1.3 COMM-008.

    BUG FIX (this pass, real runtime 500 confirmed during manual testing):
    `posts.updated_at` has `onupdate=func.now()` — a server-computed value.
    SQLAlchemy deliberately expires that ONE attribute on the instance after
    any UPDATE that changes it (regardless of the session's `expire_on_commit`
    setting, which is already `False` in core/db.py and is NOT the bug), since
    the value in memory is now known-stale. The caller (community/router.py's
    `patch_post`) then calls `serialize_post(db, post)`, which reads
    `post.updated_at` — triggering an implicit lazy-refresh that crashes with
    `MissingGreenlet` under AsyncSession, because that refresh isn't wrapped
    in an explicit `await`. Fixed with one explicit `await db.refresh(post)`
    right after commit, so the attribute is genuinely re-fetched (correctly,
    inside an awaited call) before this function returns — not hidden, not
    worked around with a broad except."""
    post = await get_post_or_404(db, post_id)
    _require_author(post, actor_id)
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Post content cannot be empty.", 400, fields={"content": "required"})
    post.content = content
    post.is_edited = True
    await db.commit()
    await db.refresh(post)
    return post


async def delete_post(db: AsyncSession, *, post_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    """§4.1.4 PCR-002 — self soft-delete. `moderation_actions.moderator_id = author_id`
    distinguishes this from a moderator-initiated removal, per Architecture §10.1's
    explicit note."""
    post = await get_post_or_404(db, post_id)
    _require_author(post, actor_id)
    if post.status == "removed":
        raise QFinanceAPIError("ALREADY_REMOVED", "This post has already been removed.", 400)

    previous_state = post.status
    post.status = "removed"

    await db.execute(
        text(
            "INSERT INTO moderation_actions "
            "(id, moderator_id, target_type, target_id, action, previous_state, new_state, reason) "
            "VALUES (:id, :moderator_id, 'post', :target_id, 'remove', :previous_state, 'removed', :reason)"
        ),
        {
            "id": str(uuid.uuid4()), "moderator_id": str(actor_id), "target_id": str(post.id),
            "previous_state": previous_state, "reason": "Self-delete by author.",
        },
    )
    await write_audit_log(
        db, actor_id=actor_id, action_type="post.self_delete", target_entity_type="post",
        target_entity_id=post.id, before_state={"status": previous_state}, after_state={"status": "removed"},
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Research-linked discussion (§4.1.5/§4.1.6, OD-14)
# ---------------------------------------------------------------------------

async def list_research_discussion(db: AsyncSession, *, research_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
    total = (await db.execute(
        select(func.count()).select_from(Post).where(Post.research_id == research_id, Post.status == "visible")
    )).scalar_one()
    rows = (await db.execute(
        select(Post).where(Post.research_id == research_id, Post.status == "visible")
        .order_by(Post.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return [await serialize_post(db, p) for p in rows], total


async def create_research_discussion_post(db: AsyncSession, *, actor_id: uuid.UUID, research_id: uuid.UUID,
                                           content: str, post_type: str = "general") -> Post:
    """§4.1.6/OD-14 — creates a `posts` row with `research_id` set, `channel=NULL`
    (satisfies `ck_posts_channel_or_research`). Emits `post_created` only —
    `research_commented` fires from the comment endpoint (§4.2.2), never here,
    per Architecture §21.2's exact rule (preserved deliberately, see that
    endpoint's docstring).

    `post_type` defaults to 'general' (unchanged behavior for every existing
    caller of this function — the plain research-discussion POST endpoint).
    V2's `POST /research/{id}/publish-to-community` (research/service.py's
    `publish_to_community`) is the only caller that passes `post_type='thesis'`.
    """
    validate_post_type(post_type)
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Post content cannot be empty.", 400, fields={"content": "required"})

    post = Post(id=uuid.uuid4(), author_id=actor_id, channel=None, research_id=research_id,
                post_type=post_type, content=content, status="visible")
    db.add(post)
    await db.flush()

    await _auto_flag_if_needed(db, target_type="post", target_id=post.id, author_id=actor_id, content=content)
    await emit_event(db, user_id=actor_id, event_type="post_created", entity_type="post", entity_id=post.id)
    await db.commit()
    return post


# ---------------------------------------------------------------------------
# Comments (§4.2)
# ---------------------------------------------------------------------------

async def serialize_comment(db: AsyncSession, comment: Comment) -> dict:
    author = await _load_author(db, comment.author_id)
    return {
        "id": str(comment.id), "post_id": str(comment.post_id),
        "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
        "author": author, "content": comment.content,
        "created_at": comment.created_at, "is_edited": comment.is_edited, "status": comment.status,
    }


async def list_comments(db: AsyncSession, *, post_id: uuid.UUID, viewer_id: uuid.UUID | None, is_staff: bool,
                         page: int, page_size: int, include_moderated: bool = False) -> tuple[list[dict], int]:
    """§4.2.1 — 'Same visibility as the parent post': the parent post itself
    must be accessible to the caller (via `_visible_to`, unaffected by
    `include_moderated` — that gate is about whether staff can act on/view a
    restricted post at all, independent of the bulk-listing override) before
    its comments are shown at all.

    Per-comment filtering within an accessible post's comment list, however,
    uses the same staff-only `include_moderated` override as
    list_channel_posts/research's list_library (API Spec §10 end note): by
    default only 'visible' comments are listed (even for staff, so staff
    don't stumble into restricted/removed comments without deliberately
    requesting them); `include_moderated=true` from a MODERATOR/ADMIN/
    SUPER_ADMIN caller additionally includes 'restricted'/'removed' comments.
    This is a behavior change from the comment list's previous per-item
    `_visible_to` filtering (which implicitly showed staff 'restricted'
    comments with no flag, and never showed 'removed' to anyone) — recorded
    explicitly in work_memory.md as a deliberate consistency fix, not a
    silent regression."""
    post = await get_post_or_404(db, post_id)
    if not _visible_to(post, viewer_id=viewer_id, is_staff=is_staff):
        raise NotFound("Post not found.")

    effective_include_moderated = include_moderated and is_staff
    statuses = ("visible", "restricted", "removed") if effective_include_moderated else ("visible",)

    all_rows = (await db.execute(
        select(Comment).where(Comment.post_id == post_id).order_by(Comment.created_at.asc())
    )).scalars().all()
    visible_rows = [c for c in all_rows if c.status in statuses]
    total = len(visible_rows)
    page_rows = visible_rows[(page - 1) * page_size: (page - 1) * page_size + page_size]
    return [await serialize_comment(db, c) for c in page_rows], total


async def create_comment(db: AsyncSession, *, actor_id: uuid.UUID, post_id: uuid.UUID, content: str) -> Comment:
    """§4.2.2. Emits `research_commented` iff the parent post's `research_id
    IS NOT NULL` — Architecture §21.2's exact rule, the mechanism that
    distinguishes OD-09's 'substantive research comment' from an ordinary
    general-channel comment (which emits no event at all, per ANLY-001's
    list having no generic comment-created event)."""
    post = await get_post_or_404(db, post_id)
    if not _visible_to(post, viewer_id=actor_id, is_staff=False):
        raise NotFound("Post not found.")
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Comment content cannot be empty.", 400, fields={"content": "required"})

    comment = Comment(id=uuid.uuid4(), post_id=post_id, author_id=actor_id, content=content, status="visible")
    db.add(comment)
    await db.flush()

    await _auto_flag_if_needed(db, target_type="comment", target_id=comment.id, author_id=actor_id, content=content)
    if post.research_id is not None:
        await emit_event(db, user_id=actor_id, event_type="research_commented",
                          entity_type="research", entity_id=post.research_id)
    await db.commit()

    # Architecture V2 §7 contribution hook — see add_reaction's identical pattern/rationale above.
    try:
        from app.modules.contributions import service as contributions_service
        await contributions_service.record_engagement_received(
            db, author_id=post.author_id, actor_id=actor_id, target_id=comment.id, engagement_label="Comment",
        )
    except Exception:
        logging.getLogger("qfinance.community").exception(
            "Unexpected error recording engagement_received contribution for comment_id=%s actor_id=%s",
            comment.id, actor_id,
        )
    return comment


async def create_reply(db: AsyncSession, *, actor_id: uuid.UUID, comment_id: uuid.UUID, content: str) -> Comment:
    """V2 API Spec §3's `POST /community/comments/{comment_id}/replies` — same
    auth/validation/visibility/event rules as `create_comment` (this function
    delegates the actual row-creation logic there rather than duplicating
    it), except `post_id` is inherited from the parent comment (never taken
    from the client) and `parent_comment_id` is set. No depth limit
    (Architecture V2 §4) — a reply-to-a-reply is valid; the parent for THAT
    reply is the reply just created, not walked up to the thread root.
    """
    parent_comment = await get_comment_or_404(db, comment_id)
    post = await get_post_or_404(db, parent_comment.post_id)
    if not _visible_to(post, viewer_id=actor_id, is_staff=False):
        raise NotFound("Post not found.")
    if not _visible_to(parent_comment, viewer_id=actor_id, is_staff=False):
        raise NotFound("Comment not found.")
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Comment content cannot be empty.", 400, fields={"content": "required"})

    reply = Comment(
        id=uuid.uuid4(), post_id=parent_comment.post_id, author_id=actor_id,
        parent_comment_id=parent_comment.id, content=content, status="visible",
    )
    db.add(reply)
    await db.flush()

    await _auto_flag_if_needed(db, target_type="comment", target_id=reply.id, author_id=actor_id, content=content)
    if post.research_id is not None:
        await emit_event(db, user_id=actor_id, event_type="research_commented",
                          entity_type="research", entity_id=post.research_id)
    await db.commit()
    return reply


async def get_comment_or_404(db: AsyncSession, comment_id: uuid.UUID) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise NotFound("Comment not found.")
    return comment


async def patch_comment(db: AsyncSession, *, comment_id: uuid.UUID, actor_id: uuid.UUID, content: str) -> Comment:
    """Same fix and reasoning as patch_post above — `comments.updated_at` has
    the identical `onupdate=func.now()` server-side-expiry pitfall, and
    router.py's `patch_comment` endpoint calls `serialize_comment(db, comment)`
    immediately after this returns, which would hit the same MissingGreenlet
    crash without this fix. Not independently reported yet (only patch_post
    was hit during manual testing), but it is the identical latent bug —
    fixed here proactively rather than left for the next crash report."""
    comment = await get_comment_or_404(db, comment_id)
    _require_author(comment, actor_id)
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Comment content cannot be empty.", 400, fields={"content": "required"})
    comment.content = content
    comment.is_edited = True
    await db.commit()
    await db.refresh(comment)
    return comment


async def delete_comment(db: AsyncSession, *, comment_id: uuid.UUID, actor_id: uuid.UUID) -> None:
    comment = await get_comment_or_404(db, comment_id)
    _require_author(comment, actor_id)
    if comment.status == "removed":
        raise QFinanceAPIError("ALREADY_REMOVED", "This comment has already been removed.", 400)

    previous_state = comment.status
    comment.status = "removed"

    await db.execute(
        text(
            "INSERT INTO moderation_actions "
            "(id, moderator_id, target_type, target_id, action, previous_state, new_state, reason) "
            "VALUES (:id, :moderator_id, 'comment', :target_id, 'remove', :previous_state, 'removed', :reason)"
        ),
        {
            "id": str(uuid.uuid4()), "moderator_id": str(actor_id), "target_id": str(comment.id),
            "previous_state": previous_state, "reason": "Self-delete by author.",
        },
    )
    await write_audit_log(
        db, actor_id=actor_id, action_type="comment.self_delete", target_entity_type="comment",
        target_entity_id=comment.id, before_state={"status": previous_state}, after_state={"status": "removed"},
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Reactions (§4.3)
# ---------------------------------------------------------------------------

async def _target_exists_and_matches(db: AsyncSession, *, target_type: str, target_id: uuid.UUID) -> bool:
    """Architecture AD-13's required application-level check before inserting a
    polymorphic-target row (no DB FK possible across `reactions.target_id`)."""
    if target_type == "post":
        return await db.get(Post, target_id) is not None
    if target_type == "comment":
        return await db.get(Comment, target_id) is not None
    return False


async def add_reaction(db: AsyncSession, *, actor_id: uuid.UUID, target_type: str, target_id: uuid.UUID,
                        reaction_type: str = "like") -> Reaction:
    if target_type not in VALID_TARGET_TYPES:
        raise QFinanceAPIError("INVALID_TARGET_TYPE", f"target_type must be one of {VALID_TARGET_TYPES}.", 400)
    if reaction_type != "like":
        raise QFinanceAPIError("INVALID_REACTION_TYPE", "reaction_type must be 'like' (MVP has one type).", 400)

    target_author_id: uuid.UUID | None = None
    if target_type == "post":
        target = await db.get(Post, target_id)
    else:
        target = await db.get(Comment, target_id)
    if target is not None and _visible_to(target, viewer_id=actor_id, is_staff=False):
        target_author_id = target.author_id
    if target_author_id is None:
        raise NotFound(f"{target_type.capitalize()} not found.")

    existing = (await db.execute(
        select(Reaction).where(
            Reaction.user_id == actor_id, Reaction.target_type == target_type,
            Reaction.target_id == target_id, Reaction.reaction_type == reaction_type,
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise QFinanceAPIError("ALREADY_REACTED", "You have already reacted to this.", 409)

    reaction = Reaction(id=uuid.uuid4(), user_id=actor_id, target_type=target_type,
                         target_id=target_id, reaction_type=reaction_type)
    db.add(reaction)
    # No event emitted — reactions are deliberately untracked in `events` (Architecture §21.2).
    await db.commit()
    # Detach before the contribution hook: a duplicate-credit no-op rolls the
    # session back, which would expire this already-committed object and
    # crash the caller's `reaction.id` read (seen on unlike -> re-like).
    db.expunge(reaction)

    # Architecture V2 §7 contribution hook. Deferred import (avoids a
    # module-load-time cross-import; `contributions` never imports `community`).
    # Runs AFTER the primary commit, so a contribution-recording failure never
    # rolls back or blocks the reaction itself — the like is the primary
    # action; the credit is a secondary side effect. The ONLY expected failure
    # mode (an idempotent replay) is already handled INSIDE
    # contributions.service._record via a specific IntegrityError catch and
    # returns None there — it never raises for that case. Anything else
    # reaching this except block is a genuine, unexpected bug and is logged
    # loudly, not silently discarded.
    try:
        from app.modules.contributions import service as contributions_service
        await contributions_service.record_engagement_received(
            db, author_id=target_author_id, actor_id=actor_id, target_id=target_id, engagement_label="Like",
        )
    except Exception:
        logging.getLogger("qfinance.community").exception(
            "Unexpected error recording engagement_received contribution for reaction target_id=%s actor_id=%s",
            target_id, actor_id,
        )
    return reaction


async def remove_reaction(db: AsyncSession, *, actor_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None:
    reaction = (await db.execute(
        select(Reaction).where(
            Reaction.user_id == actor_id, Reaction.target_type == target_type,
            Reaction.target_id == target_id, Reaction.reaction_type == "like",
        )
    )).scalar_one_or_none()
    if reaction is None:
        raise NotFound("Reaction not found.")
    await db.delete(reaction)
    await db.commit()


# ---------------------------------------------------------------------------
# Bookmarks (§4.4, COMM-006/AD-09)
# ---------------------------------------------------------------------------

async def add_bookmark(db: AsyncSession, *, actor_id: uuid.UUID, post_id: uuid.UUID) -> Bookmark:
    post = await db.get(Post, post_id)
    if post is None or not _visible_to(post, viewer_id=actor_id, is_staff=False):
        raise NotFound("Post not found.")
    existing = (await db.execute(
        select(Bookmark).where(Bookmark.user_id == actor_id, Bookmark.post_id == post_id)
    )).scalar_one_or_none()
    if existing is not None:
        raise QFinanceAPIError("ALREADY_BOOKMARKED", "You have already bookmarked this post.", 409)
    bookmark = Bookmark(id=uuid.uuid4(), user_id=actor_id, post_id=post_id)
    db.add(bookmark)
    await db.commit()
    return bookmark


async def remove_bookmark(db: AsyncSession, *, actor_id: uuid.UUID, post_id: uuid.UUID) -> None:
    bookmark = (await db.execute(
        select(Bookmark).where(Bookmark.user_id == actor_id, Bookmark.post_id == post_id)
    )).scalar_one_or_none()
    if bookmark is None:
        raise NotFound("Bookmark not found.")
    await db.delete(bookmark)
    await db.commit()


async def list_bookmarks(db: AsyncSession, *, actor_id: uuid.UUID, page: int, page_size: int) -> tuple[list[dict], int]:
    total = (await db.execute(
        select(func.count()).select_from(Bookmark).where(Bookmark.user_id == actor_id)
    )).scalar_one()
    rows = (await db.execute(
        select(Bookmark).where(Bookmark.user_id == actor_id)
        .order_by(Bookmark.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    items = []
    for b in rows:
        post = await db.get(Post, b.post_id)
        # A removed/restricted post's text must not resurface through Saved.
        visible = post is not None and _visible_to(post, viewer_id=actor_id, is_staff=False)
        summary = post.content[:140] if visible else "This post is no longer available."
        items.append({
            "post_id": str(b.post_id), "post_summary": summary, "bookmarked_at": b.created_at,
            "post_type": post.post_type if visible else None, "available": visible,
        })
    return items, total
