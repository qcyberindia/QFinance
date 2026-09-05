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
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.errors import Forbidden, NotFound, QFinanceAPIError
from app.modules.analytics.models import emit_event
from app.modules.community.models import CHANNELS, Bookmark, Comment, Post, Reaction
from app.modules.users import service as users_service

VALID_TARGET_TYPES = ("post", "comment")


async def _load_author(db: AsyncSession, author_id: uuid.UUID) -> dict:
    row = (await db.execute(
        text("SELECT user_id, name, username FROM profiles WHERE user_id = :uid"), {"uid": str(author_id)},
    )).first()
    return ({"id": str(row.user_id), "name": row.name, "username": row.username} if row
            else {"id": str(author_id), "name": None, "username": None})


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


async def serialize_post(db: AsyncSession, post: Post) -> dict:
    author = await _load_author(db, post.author_id)
    reaction_count, comment_count = await _post_counts(db, post.id)
    return {
        "id": str(post.id), "channel": post.channel, "research_id": str(post.research_id) if post.research_id else None,
        "author": author, "content": post.content, "created_at": post.created_at, "updated_at": post.updated_at,
        "is_edited": post.is_edited, "status": post.status,
        "reaction_count": reaction_count, "comment_count": comment_count,
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


async def create_channel_post(db: AsyncSession, *, actor_id: uuid.UUID, channel: str, content: str) -> Post:
    """§4.1.2. CMPL-004 first-post gate + MOD-003 flagged-phrase signal."""
    validate_channel(channel)
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Post content cannot be empty.", 400, fields={"content": "required"})

    if not await users_service.has_acknowledged_current_charter(db, user_id=actor_id):
        raise QFinanceAPIError(
            "CHARTER_NOT_ACKNOWLEDGED",
            "You must acknowledge the Member Charter before posting.", 403,
        )

    post = Post(id=uuid.uuid4(), author_id=actor_id, channel=channel, research_id=None, content=content, status="visible")
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
    """§4.1.3 COMM-008."""
    post = await get_post_or_404(db, post_id)
    _require_author(post, actor_id)
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Post content cannot be empty.", 400, fields={"content": "required"})
    post.content = content
    post.is_edited = True
    await db.commit()
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
                                           content: str) -> Post:
    """§4.1.6/OD-14 — creates a `posts` row with `research_id` set, `channel=NULL`
    (satisfies `ck_posts_channel_or_research`). Emits `post_created` only —
    `research_commented` fires from the comment endpoint (§4.2.2), never here,
    per Architecture §21.2's exact rule (preserved deliberately, see that
    endpoint's docstring)."""
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Post content cannot be empty.", 400, fields={"content": "required"})

    post = Post(id=uuid.uuid4(), author_id=actor_id, channel=None, research_id=research_id, content=content, status="visible")
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
        "id": str(comment.id), "post_id": str(comment.post_id), "author": author, "content": comment.content,
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
    return comment


async def get_comment_or_404(db: AsyncSession, comment_id: uuid.UUID) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise NotFound("Comment not found.")
    return comment


async def patch_comment(db: AsyncSession, *, comment_id: uuid.UUID, actor_id: uuid.UUID, content: str) -> Comment:
    comment = await get_comment_or_404(db, comment_id)
    _require_author(comment, actor_id)
    if not content or not content.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "Comment content cannot be empty.", 400, fields={"content": "required"})
    comment.content = content
    comment.is_edited = True
    await db.commit()
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
    if not await _target_exists_and_matches(db, target_type=target_type, target_id=target_id):
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
    if await db.get(Post, post_id) is None:
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
        summary = (post.content[:140] if post else "")
        items.append({"post_id": str(b.post_id), "post_summary": summary, "bookmarked_at": b.created_at})
    return items, total
