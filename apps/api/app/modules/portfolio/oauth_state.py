"""Zerodha OAuth `state` — binds a broker callback to the Qfinera session that
started the connection, so a callback URL can't link someone's Zerodha
account to a different logged-in member.

Same pattern as auth/token_store.py (Redis, opaque random token, atomic
single-use consumption):

- the state is `secrets.token_urlsafe(32)` (256 bits) — no user id, email or
  timestamp in it;
- Redis stores it under a SHA-256 of the state (the raw value is never a key
  and never logged), with the initiating user id and a SHA-256 of that
  session's cookie;
- it expires after STATE_TTL_SECONDS and is consumed with GETDEL, so it can
  be used once at most — even a rejected attempt burns it.
"""
import hashlib
import json
import secrets
import uuid

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

_PREFIX = "qf:broker_oauth_state:"
STATE_TTL_SECONDS = 600  # long enough to log in at Zerodha, short enough to limit replay


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def create_state(*, user_id: uuid.UUID, session_token: str) -> str:
    state = secrets.token_urlsafe(32)
    payload = json.dumps({"user_id": str(user_id), "session": _digest(session_token)})
    await _redis.set(_PREFIX + _digest(state), payload, ex=STATE_TTL_SECONDS)
    return state


async def consume_state(*, state: str, user_id: uuid.UUID, session_token: str) -> bool:
    """True only if `state` exists, has not expired or been used, and was
    created by this same user in this same session. Always consumes it."""
    if not state or len(state) > 128:
        return False
    raw = await _redis.getdel(_PREFIX + _digest(state))
    if not raw:
        return False
    try:
        bound = json.loads(raw)
    except ValueError:
        return False
    return (
        secrets.compare_digest(bound.get("user_id", ""), str(user_id))
        and secrets.compare_digest(bound.get("session", ""), _digest(session_token))
    )
