"""Redis-backed, single-use tokens for email verification (AUTH-002) and password
reset (AUTH-005/006) — same architectural pattern as `session_store.py` (AD-03):
opaque token, server-side state in Redis, nothing sensitive in the token itself
beyond its own unguessability.

Single-use is enforced by deleting the key on successful consumption (`consume_*`),
not merely on expiry — a token that's already been used once is gone immediately,
not just eventually. This directly implements API Spec §1.6's "invalidates the token
after use."

TTLs are implementation-level choices not spelled out numerically in the locked
docs (API Spec §1.2/§1.6 specify the *behavior* — invalid/expired token rejected —
not an exact duration). Chosen using ordinary industry defaults for this kind of
token, not a specification requirement: 24 hours for email verification (long enough
that a new signup checking their inbox the next morning still works), 1 hour for
password reset (shorter, since a reset link is more security-sensitive and is
expected to be used promptly). Flagged here explicitly as a judgment call, not a
locked-document value, in case a future session needs to reconcile this against an
explicit requirement this session didn't have visibility into.

WRITTEN, NOT EXECUTED — no real Redis instance has been reached in this session.
"""
import secrets
from uuid import UUID

import redis.asyncio as redis

from app.core.config import get_settings

settings = get_settings()
_redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

_VERIFY_PREFIX = "qf:verify_email:"
_RESET_PREFIX = "qf:password_reset:"

VERIFY_TOKEN_TTL_SECONDS = 60 * 60 * 24       # 24 hours
RESET_TOKEN_TTL_SECONDS = 60 * 60             # 1 hour


async def create_verification_token(user_id: UUID) -> str:
    token = secrets.token_urlsafe(32)
    await _redis.set(_VERIFY_PREFIX + token, str(user_id), ex=VERIFY_TOKEN_TTL_SECONDS)
    return token


async def consume_verification_token(token: str) -> UUID | None:
    """Returns the associated user_id and deletes the token, or None if the token
    doesn't exist/already expired/already used. Uses GETDEL for an atomic
    read-and-delete — no separate GET-then-DELETE race window where the same token
    could be consumed twice by two concurrent requests."""
    user_id_str = await _redis.getdel(_VERIFY_PREFIX + token)
    return UUID(user_id_str) if user_id_str else None


async def create_password_reset_token(user_id: UUID) -> str:
    token = secrets.token_urlsafe(32)
    await _redis.set(_RESET_PREFIX + token, str(user_id), ex=RESET_TOKEN_TTL_SECONDS)
    return token


async def consume_password_reset_token(token: str) -> UUID | None:
    user_id_str = await _redis.getdel(_RESET_PREFIX + token)
    return UUID(user_id_str) if user_id_str else None
