"""Redis-backed pending-checkout store — API Spec §3.2.1's resolution of Architecture
§17 Remaining Technical Question #5. A Razorpay order is created and its pending
(user_id, plan_code) association is held here, short-TTL, keyed by
`razorpay_order_id`, until the webhook (§3.2.2) confirms payment and promotes it into
a real `subscriptions` row. This keeps `subscriptions` meaning "confirmed billing
history" only, never "attempted-but-unconfirmed" — no `pending` value is added to
`subscriptions.status`'s CHECK constraint.

Same pattern as `auth/session_store.py` — reused deliberately, not reinvented.

WRITTEN, NOT EXECUTED — no real Redis instance has been reached in this session.
"""
import json
from uuid import UUID

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

_KEY_PREFIX = "qf:pending_checkout:"
_TTL_SECONDS = 60 * 30  # 30 minutes — long enough for a checkout session, short enough
                         # not to accumulate stale abandoned-checkout keys indefinitely.


async def create_pending_checkout(*, order_id: str, user_id: UUID, plan_code: str, amount_paise: int) -> None:
    payload = {"user_id": str(user_id), "plan_code": plan_code, "amount_paise": amount_paise}
    await _redis.set(_KEY_PREFIX + order_id, json.dumps(payload), ex=_TTL_SECONDS)


async def get_pending_checkout(order_id: str) -> dict | None:
    raw = await _redis.get(_KEY_PREFIX + order_id)
    if raw is None:
        return None
    data = json.loads(raw)
    data["user_id"] = UUID(data["user_id"])
    return data


async def clear_pending_checkout(order_id: str) -> None:
    await _redis.delete(_KEY_PREFIX + order_id)
