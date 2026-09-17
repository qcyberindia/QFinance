"""Profile business logic — API Specification V2 §6 (P.1), PRD V2 §4.7.
No `profile` module models.py exists — this is a read-only aggregation over
`profiles`/`posts`/`contributions`, all owned by other modules, read via raw
SQL rather than cross-module ORM imports (the same pattern already
established by companies/service.py's get_content_counts and
research/service.py's _load_author_and_company).
WRITTEN, NOT EXECUTED.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound

DEFAULT_RECENT_POSTS_LIMIT = 10


async def get_public_profile(db: AsyncSession, *, username: str) -> dict:
    """SECURITY FIX (this pass): previously selected and returned `profiles.name`
    (the user's real display name, collected at registration) directly in this
    PUBLIC, unauthenticated endpoint's response — a live violation of the
    explicit 'never auto-connect real identity → public community identity'
    requirement. `name` is no longer selected from the database here at all
    (not just dropped from the response) — the query itself now only reads
    `bio`, so there's no real-name value in scope to leak even if a future
    change to the return dict got careless. `username` IS the public,
    pseudonymous identity (already a separate, independently-chosen, unique
    CITEXT column from `name` — Architecture already supports pseudonymous
    handles like 'Investor_4821' today; this pass does not add automatic
    pseudonym GENERATION, which would need its own schema/UX decision and is
    out of scope for this fix — see work_memory.md)."""
    profile_row = (await db.execute(
        text("SELECT user_id, bio FROM profiles WHERE username = :username"),
        {"username": username},
    )).first()
    if profile_row is None:
        raise NotFound("Profile not found.")

    user_id = profile_row.user_id

    # Only 'visible' posts count publicly — matches the same moderation-status
    # visibility rule community/service.py's _visible_to applies everywhere
    # else, so a restricted/removed post never inflates a public count or
    # appears in the recent-posts list.
    published_posts_count = (await db.execute(
        text("SELECT COUNT(*) FROM posts WHERE author_id = :uid AND status = 'visible'"),
        {"uid": str(user_id)},
    )).scalar_one()
    published_theses_count = (await db.execute(
        text("SELECT COUNT(*) FROM posts WHERE author_id = :uid AND status = 'visible' AND post_type = 'thesis'"),
        {"uid": str(user_id)},
    )).scalar_one()
    contribution_points = (await db.execute(
        text("SELECT COALESCE(SUM(points), 0) FROM contributions WHERE user_id = :uid"),
        {"uid": str(user_id)},
    )).scalar_one()
    recent_rows = (await db.execute(
        text(
            "SELECT id, post_type, content, created_at FROM posts "
            "WHERE author_id = :uid AND status = 'visible' "
            "ORDER BY created_at DESC LIMIT :lim"
        ),
        {"uid": str(user_id), "lim": DEFAULT_RECENT_POSTS_LIMIT},
    )).all()

    return {
        "username": username,
        "bio": profile_row.bio,
        "published_posts_count": published_posts_count,
        "published_theses_count": published_theses_count,
        "contribution_points": int(contribution_points),
        "recent_posts": [
            {"id": str(r.id), "post_type": r.post_type, "content": r.content, "created_at": r.created_at}
            for r in recent_rows
        ],
    }
