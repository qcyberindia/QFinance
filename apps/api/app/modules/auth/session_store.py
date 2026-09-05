"""
Redis-backed session store (AD-03). Session id lives in the HttpOnly qf_session
cookie; the actual session data (user_id, issued_at) is server-side in Redis,
enabling immediate revocation on suspension/password-change (unlike a bare JWT).
WRITTEN, NOT EXECUTED — no real Redis instance has been reached in this session.
"""
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

_KEY_PREFIX = "qf:session:"


async def create_session(user_id: UUID) -> str:
    from app.core.security import generate_session_token

    token = generate_session_token()
    payload = {"user_id": str(user_id), "issued_at": datetime.now(timezone.utc).isoformat()}
    await _redis.set(_KEY_PREFIX + token, json.dumps(payload), ex=settings.SESSION_TTL_SECONDS)
    return token


async def get_session(token: str) -> dict[str, Any] | None:
    raw = await _redis.get(_KEY_PREFIX + token)
    if raw is None:
        return None
    data = json.loads(raw)
    data["user_id"] = UUID(data["user_id"])
    return data


async def destroy_session(token: str) -> None:
    await _redis.delete(_KEY_PREFIX + token)


async def destroy_all_sessions_for_user(user_id: UUID) -> None:
    """Used on password-reset confirm (API Spec §1.6) — forces re-login everywhere,
    a deliberate security default per AD-03's revocation-friendly design.
    NOTE: this naive scan is fine at MVP scale; a production implementation would
    maintain a secondary per-user session-id set for O(1) invalidation instead of
    SCAN — flagged here rather than silently left as a hidden perf cliff."""
    async for key in _redis.scan_iter(match=f"{_KEY_PREFIX}*"):
        raw = await _redis.get(key)
        if raw and json.loads(raw).get("user_id") == str(user_id):
            await _redis.delete(key)
