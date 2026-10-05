"""Contributions/Credits business logic — Architecture V2 §7, PRD V2 §4.8.
WRITTEN, NOT EXECUTED.

FORMULA (deliberately simple, deterministic, and defined in exactly one
place — per the explicit "keep it simple and configurable" instruction, not
an ML/recommendation system):

  thesis_published      -> 100 points
  engagement_received   ->   5 points  (one like OR one comment received on
                                          your content)
  rating_received       ->  10 points  (one rating received on your thesis)

Q-POINTS ARE NOT MONEY. They are a reputation/contribution score only — no
rupee or paise value, no balance, no credit ledger, no redemption, no
transfer, and no effect on any price. (An earlier revision converted points
to paise and wrote `credit_ledger` rows; that monetary interpretation was
removed. The `credit_ledger` table is no longer written or read.)

IDEMPOTENCY — the actual fix this revision makes, replacing an earlier,
genuinely incorrect design:

The dedup identity is (actor_id, source_type, source_entity_id) — WHO
performed the action, WHAT KIND of action, and WHICH specific object —
enforced by a real database UNIQUE constraint
(`ux_contributions_actor_event_target`, alembic/versions/0006), not just
application logic. This is deliberately NOT (source_type, source_entity_id)
alone, which would have wrongly prevented two different members from each
earning credit for engaging with the same post, and NOT (actor_id,
source_type) alone, which would have wrongly prevented the same member from
earning credit for two genuinely different objects (e.g. two different
comments, or rating two different theses).

What this correctly allows and correctly blocks:
  - User A likes Post X, then User B likes Post X -> BOTH earn credit
    (different actor_id, same source_entity_id=Post X -> no collision).
  - User A likes Post X, unlikes, re-likes Post X -> credit earned ONCE
    only, on the first like (same actor_id + source_entity_id -> the
    second attempt collides with the first and is treated as a no-op, not
    an error surfaced to the caller).
  - User A comments twice on Post X -> BOTH earn credit (source_entity_id
    is the COMMENT's own id, which differs per comment, not the post's id
    — so these are genuinely different objects, not a repeat of the same one).
  - User A publishes-to-community for Research R, then does it again ->
    credit earned ONCE (same actor_id=user_id + source_entity_id=research
    id for `thesis_published`, where actor and beneficiary are the same
    person by definition of that event).
  - User A rates Thesis T, then changes their rating on the same thesis ->
    credit earned ONCE, on the first rating only (same actor_id + post_id).

ERROR HANDLING: `_record` only ever catches the ONE specific, expected,
anticipated condition — a unique-constraint violation on exactly this
constraint, meaning "this exact contribution was already awarded" — and
treats that as a deliberate, silent no-op (not an error). Every other
exception (a real programming bug, a database outage, a wrong foreign key)
is NOT caught here and propagates normally. Callers that treat contribution
recording as best-effort/non-blocking (see call sites in community/service.py
and ratings/service.py) are responsible for their OWN explicit,
narrowly-scoped try/except with real logging — this module itself never
silently discards an unexpected failure.
"""
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contributions.models import Contribution

logger = logging.getLogger("qfinance.contributions")

POINTS_BY_SOURCE = {
    "thesis_published": 100,
    "engagement_received": 5,
    "rating_received": 10,
}


SOURCE_LABELS = {
    "thesis_published": "Thesis published to Community",
    "engagement_received": "Engagement received",
    "rating_received": "Thesis rating received",
}


async def _record(db: AsyncSession, *, user_id: uuid.UUID, actor_id: uuid.UUID, source_type: str,
                   source_entity_id: uuid.UUID) -> Contribution | None:
    """Returns the created Contribution, or None if this exact
    (actor_id, source_type, source_entity_id) combination was already
    recorded — the ONLY condition this function treats as expected/silent.
    Writes the points row only; nothing monetary."""
    contribution = Contribution(
        id=uuid.uuid4(), user_id=user_id, actor_id=actor_id, source_type=source_type,
        source_entity_id=source_entity_id, points=POINTS_BY_SOURCE[source_type],
    )
    db.add(contribution)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return None
    await db.commit()
    return contribution


async def record_thesis_published(db: AsyncSession, *, user_id: uuid.UUID, research_id: uuid.UUID) -> Contribution | None:
    """Actor and beneficiary are the same person for this event type —
    publishing your own research to Community is the sole legitimate
    trigger. A second publish-to-community call for the same research_id by
    the same user correctly earns nothing further (see module docstring)."""
    return await _record(
        db, user_id=user_id, actor_id=user_id, source_type="thesis_published", source_entity_id=research_id
    )


async def record_engagement_received(db: AsyncSession, *, author_id: uuid.UUID, actor_id: uuid.UUID,
                                      target_id: uuid.UUID, engagement_label: str) -> Contribution | None:
    """`target_id` is the SPECIFIC object being engaged with (the post/comment
    id being liked, or the newly-created comment's OWN id for a comment
    engagement — never the parent post's id for comments, so that two
    distinct comments from the same actor on the same post are correctly
    treated as two distinct objects, not a duplicate).

    Self-engagement guard: a member liking/commenting on their own content
    earns nothing (checked here, once, so it cannot be forgotten by a future
    caller)."""
    if actor_id == author_id:
        return None
    return await _record(
        db, user_id=author_id, actor_id=actor_id, source_type="engagement_received", source_entity_id=target_id
    )


async def record_rating_received(db: AsyncSession, *, author_id: uuid.UUID, actor_id: uuid.UUID,
                                  post_id: uuid.UUID) -> Contribution | None:
    """`source_entity_id=post_id` (the thesis), not a rating row id — the
    dedup key must be stable across a rating being updated in place
    (ratings/service.py upserts rather than inserting a new row per
    re-rate), so the SAME thesis rated a second time by the same actor
    correctly collides with the first and earns nothing further."""
    if actor_id == author_id:
        return None
    return await _record(
        db, user_id=author_id, actor_id=actor_id, source_type="rating_received", source_entity_id=post_id
    )


async def get_total_points(db: AsyncSession, *, user_id: uuid.UUID) -> int:
    total = (await db.execute(
        select(func.coalesce(func.sum(Contribution.points), 0)).where(Contribution.user_id == user_id)
    )).scalar_one()
    return int(total)


async def get_points_summary(db: AsyncSession, *, user_id: uuid.UUID, page: int, page_size: int) -> dict:
    """The member's Q-Point score plus their contribution history — points
    only, never a currency amount."""
    points = await get_total_points(db, user_id=user_id)
    total = (await db.execute(
        select(func.count()).select_from(Contribution).where(Contribution.user_id == user_id)
    )).scalar_one()
    rows = (await db.execute(
        select(Contribution).where(Contribution.user_id == user_id)
        .order_by(Contribution.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {
        "points": points, "page": page, "page_size": page_size, "total": total,
        "entries": [
            {"points": c.points, "source_type": c.source_type,
             "reason": SOURCE_LABELS.get(c.source_type, c.source_type), "created_at": c.created_at}
            for c in rows
        ],
    }
