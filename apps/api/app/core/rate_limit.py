"""Tiny fixed-window rate limiter on the project's existing Redis (the same
instance sessions already depend on). Deliberately minimal: one function, no
decorator framework.

Why it exists: some endpoints make the SERVER call out to a user-supplied URL
(AI Test Connection). Even with an SSRF guard that only allows public
addresses, an unthrottled endpoint would let any account use the server as a
port-scanner / request proxy against the public internet. This bounds that.

TTL is set with SET NX EX *before* INCR (INCR preserves the TTL), so a crash
between the two calls can never leave a counter without an expiry that would
block a user forever.

FAILS OPEN if Redis errors: sessions already require Redis, so a Redis outage
breaks login long before this matters, and failing closed here would only turn
a transient blip into a feature outage. The failure is logged (bucket name
only — never the subject/key).
"""
import logging

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.errors import QFinanceAPIError

logger = logging.getLogger("qfinera.rate_limit")

_redis = redis.from_url(get_settings().REDIS_URL, decode_responses=True)


async def enforce_rate_limit(bucket: str, subject: str, *, limit: int, window_seconds: int) -> None:
    """Raise a 429 `RATE_LIMITED` QFinanceAPIError once `subject` has made more
    than `limit` calls to `bucket` within the current `window_seconds` window."""
    key = f"qf:rl:{bucket}:{subject}"
    try:
        await _redis.set(key, 0, ex=window_seconds, nx=True)
        count = await _redis.incr(key)
    except Exception:  # noqa: BLE001 — see module docstring: deliberate fail-open
        logger.warning("rate limiter unavailable; failing open for bucket=%s", bucket)
        return
    if count > limit:
        raise QFinanceAPIError(
            "RATE_LIMITED", "Too many attempts. Please wait a few minutes and try again.", 429,
        )
