"""BYOK connection management — connect/status/disconnect, and the
key-retrieval function research/service.py calls internally (never exposed
via any API response).

SECURITY FIX (this pass): this file previously read/wrote a plaintext
`connection.api_key` attribute that does not even exist on the current
`AIConnection` model (models.py already defines only `encrypted_api_key` —
see that file's own docstring) — meaning this code, as written before this
fix, would have raised `AttributeError` the first time it actually ran
against a real database, on top of being a plaintext-storage bug. It never
called `app.core.crypto.encrypt_secret`/`decrypt_secret` at all, despite
those helpers already existing. Both problems are fixed together here:
`connect()` now encrypts the member's key before it ever reaches `db.add`/
`db.commit`, and `get_active_key()` now decrypts it immediately before
handing it to the caller (`research/service.py`, per that function's own
docstring — never a router, never a response schema).
WRITTEN, NOT EXECUTED."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.crypto import DecryptionError, EncryptionNotConfiguredError, decrypt_secret, encrypt_secret
from app.core.errors import QFinanceAPIError
from app.modules.ai.models import VALID_PROVIDERS, AIConnection


async def get_connection(db: AsyncSession, *, user_id: uuid.UUID, provider: str = "anthropic") -> AIConnection | None:
    result = await db.execute(
        select(AIConnection).where(AIConnection.user_id == user_id, AIConnection.provider == provider)
    )
    return result.scalar_one_or_none()


async def connect(db: AsyncSession, *, user_id: uuid.UUID, provider: str, api_key: str) -> AIConnection:
    if provider not in VALID_PROVIDERS:
        raise QFinanceAPIError("INVALID_AI_PROVIDER", f"provider must be one of {VALID_PROVIDERS}.", 400)
    if not api_key or not api_key.strip():
        raise QFinanceAPIError("VALIDATION_ERROR", "api_key cannot be empty.", 400, fields={"api_key": "required"})

    # Encrypt BEFORE this function ever touches db.add/db.commit — the
    # plaintext `api_key` local variable is never assigned to the ORM object
    # and never persisted. If encryption isn't configured, fail the whole
    # operation (503) rather than fall back to storing the raw value.
    try:
        ciphertext = encrypt_secret(api_key)
    except EncryptionNotConfiguredError as e:
        raise QFinanceAPIError(
            "AI_ENCRYPTION_NOT_CONFIGURED",
            "AI key storage is not configured on this server. Please try again later.",
            503,
        ) from e

    existing = await get_connection(db, user_id=user_id, provider=provider)
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.encrypted_api_key = ciphertext
        existing.connected_at = now
        connection = existing
    else:
        connection = AIConnection(
            id=uuid.uuid4(), user_id=user_id, provider=provider,
            encrypted_api_key=ciphertext, connected_at=now,
        )
        db.add(connection)

    # Audit the CONNECTION EVENT only — never the key itself, plaintext or
    # ciphertext (ciphertext is still a secret-derived value worth keeping
    # out of the audit trail entirely, not just "safe because it's encrypted").
    await write_audit_log(
        db, actor_id=user_id, action_type="ai.connected", target_entity_type="ai_connection",
        target_entity_id=connection.id if existing else connection.id,
        after_state={"provider": provider},
    )
    await db.commit()
    return connection


async def disconnect(db: AsyncSession, *, user_id: uuid.UUID, provider: str = "anthropic") -> None:
    connection = await get_connection(db, user_id=user_id, provider=provider)
    if connection is None:
        return
    await write_audit_log(
        db, actor_id=user_id, action_type="ai.disconnected", target_entity_type="ai_connection",
        target_entity_id=connection.id, before_state={"provider": provider},
    )
    await db.delete(connection)
    await db.commit()


async def get_status(db: AsyncSession, *, user_id: uuid.UUID, provider: str = "anthropic") -> dict:
    connection = await get_connection(db, user_id=user_id, provider=provider)
    if connection is None:
        return {"connected": False, "provider": None, "connected_at": None}
    return {"connected": True, "provider": connection.provider, "connected_at": connection.connected_at}


async def get_active_key(db: AsyncSession, *, user_id: uuid.UUID, provider: str = "anthropic") -> str:
    """Internal-only — called by research/service.py, never by a router
    directly, and its return value must never be placed into any Pydantic
    response model. Decrypts immediately before returning; the caller is
    expected to pass the result straight to the provider adapter and not
    hold onto it.

    Deliberately does NOT catch DecryptionError and fall back to treating
    `connection.encrypted_api_key` as if it were already plaintext — that
    would silently reintroduce the exact bug this pass fixes, just moved
    one call frame up. A decryption failure (wrong/rotated secret, or a
    genuinely corrupted row) always surfaces as a clean, non-leaking error
    instead."""
    connection = await get_connection(db, user_id=user_id, provider=provider)
    if connection is None:
        raise QFinanceAPIError("AI_NOT_CONNECTED", "Connect your AI provider to use the research assistant.", 503)
    try:
        return decrypt_secret(connection.encrypted_api_key)
    except EncryptionNotConfiguredError as e:
        raise QFinanceAPIError(
            "AI_ENCRYPTION_NOT_CONFIGURED",
            "AI key storage is not configured on this server. Please try again later.",
            503,
        ) from e
    except DecryptionError as e:
        raise QFinanceAPIError(
            "AI_KEY_UNREADABLE",
            "Your stored AI provider key could not be read. Please reconnect it.",
            409,
        ) from e
