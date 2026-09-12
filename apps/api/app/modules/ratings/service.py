"""Ratings business logic — API Specification V2 §4 (R.1-R.3).

Reads `community`'s `Post` model directly (not a service-function call) for
the `post_type`/`author_id` checks below — a read-only existence/field check,
matching the precedent already set by `billing/service.py`'s direct import of
`membership.models.Subscription` for an analogous read. No write ever touches
`posts` from this module.

Average/count are computed at read time (no materialized column on `posts`),
per Database Schema V2 §3's explicit "Deferred" note — this is a deliberate
simplicity choice, not an oversight, and is fine at MVP scale (SQL `AVG`/
`COUNT` over an indexed foreign key).

WRITTEN, NOT EXECUTED.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, QFinanceAPIError
from app.modules.community.models import Post
from app.modules.ratings.models import Rating


def _cannot_rate_own_thesis_error() -> QFinanceAPIError:
    """Named helper (not just an inline raise) so the exact CANNOT_RATE_OWN_THESIS
    error code — required verbatim by API Spec V2 §4 R.1 — has exactly one
    place it's constructed, avoiding a typo'd duplicate elsewhere."""
    return QFinanceAPIError("CANNOT_RATE_OWN_THESIS", "You cannot rate your own thesis.", 403)


async def _get_rateable_post_or_error(db: AsyncSession, post_id: uuid.UUID) -> Post:
    post = await db.get(Post, post_id)
    if post is None:
        raise NotFound("Post not found.")
    if post.post_type != "thesis":
        raise QFinanceAPIError("POST_NOT_RATEABLE", "Only thesis posts can be rated.", 400)
    return post


async def create_or_update_rating(db: AsyncSession, *, actor_id: uuid.UUID, post_id: uuid.UUID, score: int) -> Rating:
    """R.1 — upsert semantics in one call, per the locked spec's exact wording
    ('create or update in one call'). `score` is also range-checked here
    (not just at the Pydantic schema layer) — defense in depth, matching
    every other numeric/enum input in this codebase."""
    if not 1 <= score <= 5:
        raise QFinanceAPIError("VALIDATION_ERROR", "score must be between 1 and 5.", 400, fields={"score": "out_of_range"})

    post = await _get_rateable_post_or_error(db, post_id)
    if post.author_id == actor_id:
        raise _cannot_rate_own_thesis_error()

    existing = (await db.execute(
        select(Rating).where(Rating.user_id == actor_id, Rating.post_id == post_id)
    )).scalar_one_or_none()

    if existing is not None:
        existing.score = score
        rating = existing
    else:
        rating = Rating(id=uuid.uuid4(), user_id=actor_id, post_id=post_id, score=score)
        db.add(rating)

    await db.commit()
    return rating


async def remove_rating(db: AsyncSession, *, actor_id: uuid.UUID, post_id: uuid.UUID) -> None:
    """R.2 — 'Removes caller's own rating.' Ownership is structural: the
    lookup is scoped to `(actor_id, post_id)`, so there is no code path where
    a caller could remove anyone else's rating even by guessing another
    user's rating existed — the query simply wouldn't find it."""
    rating = (await db.execute(
        select(Rating).where(Rating.user_id == actor_id, Rating.post_id == post_id)
    )).scalar_one_or_none()
    if rating is None:
        raise NotFound("Rating not found.")
    await db.delete(rating)
    await db.commit()


async def get_rating_summary(db: AsyncSession, *, post_id: uuid.UUID) -> dict:
    """R.3 — Authenticated only (any tier), per the locked spec; no post_type
    check here (a caller can query a summary even for a non-thesis post,
    which will just correctly show count=0 — no error, since 'is this
    rateable' and 'what does its rating summary look like' are different
    questions and the spec doesn't gate R.3 on post_type)."""
    if await db.get(Post, post_id) is None:
        raise NotFound("Post not found.")
    result = (await db.execute(
        select(func.avg(Rating.score), func.count(Rating.id)).where(Rating.post_id == post_id)
    )).first()
    average, count = result
    return {"average": float(average) if average is not None else None, "count": count or 0}
