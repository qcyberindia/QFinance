"""BYOK connection management — connect/status/disconnect/list, connection
testing, and provider resolution for the (future) Research Assistant.

SECURITY MODEL (unchanged rules, now covering three providers):
- The API key is encrypted (app/core/crypto.py, Fernet) BEFORE it touches the
  ORM object; the plaintext local never reaches db.add/commit. If encryption
  isn't configured the whole operation fails (503) — no plaintext fallback.
- Nothing in this module returns, logs, audits, or embeds a key (plaintext or
  ciphertext) in any response/exception. `get_active_key` and
  `resolve_provider_for_user` are INTERNAL: they hand the decrypted key to a
  provider adapter and must never feed a response model.
- Decryption failure is never "recovered" by treating the stored value as
  plaintext (that would recreate the original bug one frame up).

OPENAI-COMPATIBLE (provider "openai_compatible"): additionally stores a
normalized base `endpoint` and a `model` (neither is a secret). The endpoint is
normalized with the adapter's single canonical rule and checked by its SSRF
guard both when SAVED and again each time it is USED. Test Connection never
sends a SAVED key to a DIFFERENT endpoint than the saved one (that would let a
caller exfiltrate their own stored key to a server they control — harmless for
their own key, but the rule keeps the stored key bound to the endpoint it was
saved with, and is what a security review would ask for).

"Active connection": there is no `is_active` column. The active connection is
defined as the user's MOST RECENTLY CONNECTED row (connected_at desc). This is
a deliberate, documented rule, not a schema change.
"""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.crypto import DecryptionError, EncryptionNotConfiguredError, decrypt_secret, encrypt_secret
from app.core.errors import QFinanceAPIError
from app.core.rate_limit import enforce_rate_limit
from app.integrations.ai_providers.base import AiProvider, AiProviderError
from app.integrations.ai_providers.openai_compatible import (
    AuthenticationFailed, EndpointUnreachable, InvalidEndpointError, InvalidProviderResponse,
    OpenAICompatibleProvider, normalize_endpoint, validate_endpoint_target,
)
from app.integrations.ai_providers.openai_provider import OpenAiProvider
from app.modules.ai.models import PROVIDER_OPENAI_COMPATIBLE, VALID_PROVIDERS, AIConnection

MAX_MODEL_LENGTH = 200
_MODEL_RE = re.compile(r"^[^\s\x00-\x1f\x7f]+$")  # model ids like qwen3:14b, dots.ocr-Q8_0, org/model

TEST_CONNECTION_LIMIT = 10
TEST_CONNECTION_WINDOW_SECONDS = 300


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _validate_model(model: str | None) -> str:
    value = (model or "").strip()
    if not value:
        raise QFinanceAPIError("VALIDATION_ERROR", "Choose or enter a model.", 400, fields={"model": "required"})
    if len(value) > MAX_MODEL_LENGTH or not _MODEL_RE.match(value):
        raise QFinanceAPIError("VALIDATION_ERROR", "That model name isn't valid.", 400, fields={"model": "invalid"})
    return value


async def _normalize_and_validate_endpoint(endpoint: str | None) -> str:
    """Canonical normalization + SSRF guard. Raises a clean 400 on any problem."""
    try:
        normalized = normalize_endpoint(endpoint or "")
        await validate_endpoint_target(normalized)
    except InvalidEndpointError as e:
        raise QFinanceAPIError("INVALID_AI_ENDPOINT", str(e), 400, fields={"endpoint": str(e)}) from e
    except EndpointUnreachable as e:
        raise QFinanceAPIError(
            "AI_ENDPOINT_UNREACHABLE", "Unable to reach AI endpoint.", 400,
            fields={"endpoint": "unreachable"},
        ) from e
    return normalized


def _normalize_only(endpoint: str | None) -> str:
    try:
        return normalize_endpoint(endpoint or "")
    except InvalidEndpointError as e:
        raise QFinanceAPIError("INVALID_AI_ENDPOINT", str(e), 400, fields={"endpoint": str(e)}) from e


def _decrypt_connection_key(connection: AIConnection) -> str:
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


def _status_dict(connection: AIConnection) -> dict:
    return {
        "connected": True, "provider": connection.provider, "connected_at": connection.connected_at,
        "endpoint": connection.endpoint, "model": connection.model,
    }


# ---------------------------------------------------------------------------
# connect / status / list / disconnect
# ---------------------------------------------------------------------------

async def get_connection(db: AsyncSession, *, user_id: uuid.UUID, provider: str = "anthropic") -> AIConnection | None:
    result = await db.execute(
        select(AIConnection).where(AIConnection.user_id == user_id, AIConnection.provider == provider)
    )
    return result.scalar_one_or_none()


async def connect(
    db: AsyncSession, *, user_id: uuid.UUID, provider: str, api_key: str,
    endpoint: str | None = None, model: str | None = None,
) -> AIConnection:
    if provider not in VALID_PROVIDERS:
        raise QFinanceAPIError("INVALID_AI_PROVIDER", f"provider must be one of {VALID_PROVIDERS}.", 400)
    api_key = (api_key or "").strip()
    if not api_key:
        raise QFinanceAPIError("VALIDATION_ERROR", "api_key cannot be empty.", 400, fields={"api_key": "required"})

    if provider == PROVIDER_OPENAI_COMPATIBLE:
        normalized_endpoint: str | None = await _normalize_and_validate_endpoint(endpoint)
        clean_model: str | None = _validate_model(model)
    else:
        if (endpoint and endpoint.strip()) or (model and model.strip()):
            raise QFinanceAPIError(
                "VALIDATION_ERROR", "endpoint and model only apply to the OpenAI-Compatible provider.", 400,
            )
        normalized_endpoint = clean_model = None

    # Encrypt BEFORE anything touches db.add/db.commit; the plaintext is never
    # assigned to the ORM object. Unconfigured encryption -> 503, never a
    # plaintext fallback.
    try:
        ciphertext = encrypt_secret(api_key)
    except EncryptionNotConfiguredError as e:
        raise QFinanceAPIError(
            "AI_ENCRYPTION_NOT_CONFIGURED",
            "AI key storage is not configured on this server. Please try again later.",
            503,
        ) from e

    existing = await get_connection(db, user_id=user_id, provider=provider)
    # Same fix as research/service.py::publish's published_at (found via a
    # real executed pytest failure this pass): ai_connections.connected_at
    # (models.py) has no timezone=True, matching every other timestamp
    # column in that file — a naive TIMESTAMP WITHOUT TIME ZONE. Storing a
    # naive UTC value here to match, rather than a tz-aware one asyncpg
    # would refuse to encode.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if existing is not None:
        existing.encrypted_api_key = ciphertext
        existing.endpoint = normalized_endpoint
        existing.model = clean_model
        existing.connected_at = now
        connection = existing
    else:
        connection = AIConnection(
            id=uuid.uuid4(), user_id=user_id, provider=provider, encrypted_api_key=ciphertext,
            endpoint=normalized_endpoint, model=clean_model, connected_at=now,
        )
        db.add(connection)

    # Audit the CONNECTION EVENT only — never the key, plaintext or ciphertext.
    await write_audit_log(
        db, actor_id=user_id, action_type="ai.connected", target_entity_type="ai_connection",
        target_entity_id=connection.id,
        after_state={"provider": provider, **({"model": clean_model} if clean_model else {})},
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
        return {"connected": False, "provider": None, "connected_at": None, "endpoint": None, "model": None}
    return _status_dict(connection)


async def list_connections(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    """The caller's own connections, most recently connected first (the first
    is the 'active' one — see module docstring). Safe metadata only."""
    rows = (await db.execute(
        select(AIConnection).where(AIConnection.user_id == user_id)
        .order_by(AIConnection.connected_at.desc(), AIConnection.id)
    )).scalars().all()
    return [_status_dict(r) for r in rows]


async def get_active_connection(db: AsyncSession, *, user_id: uuid.UUID) -> AIConnection | None:
    return (await db.execute(
        select(AIConnection).where(AIConnection.user_id == user_id)
        .order_by(AIConnection.connected_at.desc(), AIConnection.id).limit(1)
    )).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Test Connection (OpenAI-Compatible) — read-only GET {endpoint}/models
# ---------------------------------------------------------------------------

def _result(ok: bool, status: str, message: str, **extra) -> dict:
    return {"ok": ok, "status": status, "message": message, "models": [], "model_count": 0,
            "selected_model": None, "selected_model_found": None, "warning": None, **extra}


async def check_connection(
    db: AsyncSession, *, user_id: uuid.UUID, provider: str, api_key: str | None,
    endpoint: str | None, model: str | None,
) -> dict:
    """Verifies reachability, authentication and model discovery. Never saves
    anything, never returns a key, and every message is a fixed string (see
    the adapter) so no upstream text can carry a credential back."""
    if provider != PROVIDER_OPENAI_COMPATIBLE:
        raise QFinanceAPIError(
            "AI_TEST_NOT_SUPPORTED", "Test Connection is only available for the OpenAI-Compatible provider.", 400,
        )
    # Bound how often a user can make the server call out to a URL of their choosing.
    await enforce_rate_limit(
        "ai_test_connection", str(user_id), limit=TEST_CONNECTION_LIMIT, window_seconds=TEST_CONNECTION_WINDOW_SECONDS,
    )

    selected = (model or "").strip() or None
    if api_key and api_key.strip():
        key = api_key.strip()
        normalized = await _normalize_and_validate_endpoint(endpoint)
    else:
        saved = await get_connection(db, user_id=user_id, provider=provider)
        if saved is None:
            raise QFinanceAPIError(
                "VALIDATION_ERROR", "Enter your API key to test the connection.", 400, fields={"api_key": "required"},
            )
        requested = _normalize_only(endpoint) if endpoint and endpoint.strip() else saved.endpoint
        if requested != saved.endpoint:
            raise QFinanceAPIError(
                "VALIDATION_ERROR",
                "To test a different endpoint, enter the API key again — your saved key is only used with the endpoint it was saved for.",
                400, fields={"api_key": "required"},
            )
        normalized = await _normalize_and_validate_endpoint(saved.endpoint)
        key = _decrypt_connection_key(saved)
        selected = selected or saved.model

    warning = (
        "This endpoint uses plain http://, so your API key is sent unencrypted over the network. "
        "Use https:// if your endpoint supports it."
    ) if normalized.lower().startswith("http://") else None

    provider_obj = OpenAICompatibleProvider(normalized)
    try:
        models = await provider_obj.list_models(api_key=key)
    except AuthenticationFailed:
        return _result(False, "auth_failed", "Authentication failed.", warning=warning)
    except EndpointUnreachable:
        return _result(False, "unreachable", "Unable to reach AI endpoint.", warning=warning)
    except InvalidProviderResponse as e:
        return _result(False, "invalid_response", str(e), warning=warning)
    except AiProviderError as e:
        return _result(False, "invalid_response", str(e), warning=warning)

    found: bool | None = None
    if selected:
        found = selected in models
        message = (
            f"Connected — {len(models)} model{'s' if len(models) != 1 else ''} available."
            if found else f'Connection successful. Selected model "{selected[:MAX_MODEL_LENGTH]}" was not found.'
        )
    else:
        message = f"Connected — {len(models)} model{'s' if len(models) != 1 else ''} available."
    return _result(
        True, "connected", message, models=models, model_count=len(models),
        selected_model=selected, selected_model_found=found, warning=warning,
    )


# ---------------------------------------------------------------------------
# Provider resolution — what the Research Assistant will consume
# ---------------------------------------------------------------------------

def build_provider(connection: AIConnection) -> AiProvider:
    """Map a saved connection to its `AiProvider` adapter. The model/endpoint
    come from the SAVED ROW — nothing is hardcoded here or in the adapter."""
    if connection.provider == PROVIDER_OPENAI_COMPATIBLE:
        if not connection.endpoint or not connection.model:
            raise QFinanceAPIError("AI_CONNECTION_INCOMPLETE", "This AI connection is incomplete. Please reconnect it.", 409)
        return OpenAICompatibleProvider(connection.endpoint, connection.model)
    if connection.provider == "openai":
        return OpenAiProvider()
    # Anthropic has an adapter (integrations/ai/anthropic_adapter.py) but it implements a
    # different interface than `AiProvider`; unifying them is a separate, deliberate change.
    raise QFinanceAPIError(
        "AI_PROVIDER_UNSUPPORTED", "The Research Assistant can't use this AI provider yet.", 400,
    )


async def resolve_provider_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> tuple[AiProvider, str, AIConnection]:
    """INTERNAL — user's active connection -> (adapter, decrypted key, row).

    The key must go straight into `adapter.ask(...)` and never into any
    response model, log line or exception. For OpenAI-Compatible the endpoint
    is re-checked by the SSRF guard on EVERY use (DNS can change after save).
    Raises AI_NOT_CONNECTED (503) when the user has no connection."""
    connection = await get_active_connection(db, user_id=user_id)
    if connection is None:
        raise QFinanceAPIError("AI_NOT_CONNECTED", "Connect your AI provider to use the research assistant.", 503)
    if connection.provider == PROVIDER_OPENAI_COMPATIBLE:
        await _normalize_and_validate_endpoint(connection.endpoint)
    adapter = build_provider(connection)
    return adapter, _decrypt_connection_key(connection), connection


async def get_active_key(db: AsyncSession, *, user_id: uuid.UUID, provider: str = "anthropic") -> str:
    """Internal-only decrypted key for one named provider (kept for existing
    callers). Never a response value; see module docstring."""
    connection = await get_connection(db, user_id=user_id, provider=provider)
    if connection is None:
        raise QFinanceAPIError("AI_NOT_CONNECTED", "Connect your AI provider to use the research assistant.", 503)
    return _decrypt_connection_key(connection)
