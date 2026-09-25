"""BYOK AI-connection security tests — app/core/crypto.py, app/modules/ai/*.

SCOPE, matching this pass's explicit instruction: BYOK connect/status/
disconnect only. No research-AI-assistant, no /research/{id}/ai/ask, no
research AI context, no new provider abstractions — none of that is
touched or tested here.

STATUS, following this repo's own established discipline (see
test_portfolio_pure_logic.py / test_portfolio_integration.py):

- The crypto/schema/model/router tests in this file are genuinely
  collectible and runnable with no real PostgreSQL/Redis — they exercise
  `app.core.crypto` directly, and structural properties of
  `app.modules.ai.models`/`schemas`/`router` that don't require a live
  database connection (SQLAlchemy's async engine and redis-py's client are
  both lazy at construction; nothing here executes a query or a Redis
  command). I do not have execution access to this project's actual
  `.venv` from this session — I separately reproduced `app/core/crypto.py`
  byte-for-byte in an isolated sandbox with the real `cryptography` package
  installed and ran the round-trip and failure-mode logic for real there
  (round trip, ciphertext != plaintext, EncryptionNotConfiguredError on
  missing/whitespace-only secret for both encrypt and decrypt,
  DecryptionError on wrong secret) — all passed. That confirms the logic;
  it does not substitute for actually running `pytest` inside this repo's
  own `.venv`, which is what the command at the bottom of this docstring is
  for.
- The connect/get/update/disconnect/auth/ownership tests that need a real
  database row and a real session cookie are written but `@pytest.mark.skip`
  for the same reason every other integration test file in this repo is
  skipped: no real PostgreSQL/Redis has been reachable from any session to
  date (see work_memory.md). They use this repo's already-established
  `db_session`/`client`/`existing_user` fixtures (conftest.py) plus small
  local helpers for a second user and a CSRF-cookie client, rather than
  inventing a new fixture pattern.

Run:
    cd apps/api
    ./.venv/bin/python -m pytest tests/test_ai_byok.py -q
"""
import inspect

import pytest
from fastapi import Depends
from sqlalchemy import select

from app.core import crypto
from app.core.crypto import DecryptionError, EncryptionNotConfiguredError, decrypt_secret, encrypt_secret
from app.core.deps import require_csrf, require_verified_email
from app.modules.ai.models import VALID_PROVIDERS, AIConnection
from app.modules.ai.router import router as ai_router
from app.modules.ai.schemas import ConnectRequest, StatusResponse


# ---------------------------------------------------------------------------
# Isolation fixture — same technique as test_portfolio_pure_logic.py's
# `unconfigured_zerodha`: app.core.crypto does `settings = get_settings()`
# once at module-import time (a cached singleton), so tests that need a
# specific AI_KEY_ENCRYPTION_SECRET state must monkeypatch that already-
# imported object directly rather than the environment.
# ---------------------------------------------------------------------------

@pytest.fixture
def configured_encryption_secret(monkeypatch):
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", "test-only-secret-do-not-reuse")


@pytest.fixture
def unconfigured_encryption_secret(monkeypatch):
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", None)


# ---------------------------------------------------------------------------
# app/core/crypto.py — genuinely runnable, no DB/Redis involved at all
# ---------------------------------------------------------------------------

def test_round_trip_returns_original_plaintext(configured_encryption_secret):
    plaintext = "sk-ant-real-looking-secret-key-abc123"
    ciphertext = encrypt_secret(plaintext)
    assert decrypt_secret(ciphertext) == plaintext


def test_ciphertext_differs_from_plaintext(configured_encryption_secret):
    plaintext = "sk-ant-real-looking-secret-key-abc123"
    ciphertext = encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert plaintext not in ciphertext


def test_two_encryptions_of_the_same_plaintext_differ(configured_encryption_secret):
    """Fernet includes a random IV per encryption — this is also an
    implicit check that no naive deterministic scheme (e.g. plain hashing)
    was substituted for real authenticated encryption."""
    plaintext = "sk-ant-real-looking-secret-key-abc123"
    assert encrypt_secret(plaintext) != encrypt_secret(plaintext)


def test_encrypt_raises_cleanly_when_secret_unconfigured(unconfigured_encryption_secret):
    with pytest.raises(EncryptionNotConfiguredError):
        encrypt_secret("some-api-key")


def test_encrypt_raises_cleanly_when_secret_is_whitespace_only(monkeypatch):
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", "   ")
    with pytest.raises(EncryptionNotConfiguredError):
        encrypt_secret("some-api-key")


def test_decrypt_raises_cleanly_when_secret_unconfigured(configured_encryption_secret, unconfigured_encryption_secret):
    # (configured_encryption_secret fixture ordering is irrelevant here —
    # unconfigured_encryption_secret runs second and is what's in effect.)
    with pytest.raises(EncryptionNotConfiguredError):
        decrypt_secret("irrelevant-ciphertext")


def test_decrypt_raises_decryption_error_on_wrong_secret(monkeypatch):
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", "secret-one")
    ciphertext = encrypt_secret("sk-ant-real-looking-secret-key-abc123")
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", "secret-two")
    with pytest.raises(DecryptionError):
        decrypt_secret(ciphertext)


def test_decrypt_raises_decryption_error_on_tampered_ciphertext(configured_encryption_secret):
    ciphertext = encrypt_secret("sk-ant-real-looking-secret-key-abc123")
    tampered = ciphertext[:-4] + ("A" if ciphertext[-4] != "A" else "B") + ciphertext[-3:]
    with pytest.raises(DecryptionError):
        decrypt_secret(tampered)


def test_decrypt_never_silently_returns_the_stored_value_as_if_it_were_plaintext(configured_encryption_secret):
    """Direct regression test for the exact bug this pass fixed one layer up
    (ai/service.py previously reading a plaintext `api_key` attribute): a
    value that was never produced by `encrypt_secret` — i.e. a hypothetical
    leftover plaintext row — must fail decryption, never be handed back
    as-is."""
    with pytest.raises(DecryptionError):
        decrypt_secret("this-was-never-encrypted-plaintext")


# ---------------------------------------------------------------------------
# app/modules/ai/models.py — structural check, no DB connection required
# (SQLAlchemy's async engine is constructed lazily; this only inspects
# in-memory table metadata built at class-definition time)
# ---------------------------------------------------------------------------

def test_model_column_is_encrypted_api_key_not_plaintext_api_key():
    columns = {c.name for c in AIConnection.__table__.columns}
    assert "encrypted_api_key" in columns
    assert "api_key" not in columns


def test_valid_providers_matches_db_check_constraint():
    assert VALID_PROVIDERS == ("anthropic",)


# ---------------------------------------------------------------------------
# app/modules/ai/schemas.py — structural check that no response schema can
# ever leak a key field, regardless of what a future db-object-to-schema
# call site does
# ---------------------------------------------------------------------------

def test_status_response_has_no_key_shaped_field():
    field_names = set(StatusResponse.model_fields.keys())
    forbidden = {"api_key", "encrypted_api_key", "key", "secret", "token"}
    assert field_names & forbidden == set()
    assert field_names == {"connected", "provider", "connected_at"}


def test_connect_request_only_accepts_provider_and_api_key():
    """The inbound request legitimately carries `api_key` (the member is
    submitting it) — this just pins the shape so it doesn't silently grow
    other sensitive fields unnoticed."""
    assert set(ConnectRequest.model_fields.keys()) == {"provider", "api_key"}


# ---------------------------------------------------------------------------
# app/modules/ai/router.py — genuinely runnable dependency-wiring check.
# Confirms every route actually uses require_verified_email (the same
# authentication/ownership dependency portfolio/router.py and every other
# per-user module uses — user_id always comes from the resolved User, never
# a path/query param) and that both mutating routes require CSRF, by
# inspecting the real router object FastAPI will serve, not by re-reading
# the source and trusting it matches.
# ---------------------------------------------------------------------------

def _depends_on(param_default, target) -> bool:
    return isinstance(param_default, type(Depends(lambda: None))) and param_default.dependency is target


def test_every_ai_route_requires_verified_email():
    assert len(ai_router.routes) == 3  # connect (POST), status (GET), connect (DELETE)
    for route in ai_router.routes:
        sig = inspect.signature(route.endpoint)
        depends_on_verified_email = any(
            _depends_on(p.default, require_verified_email) for p in sig.parameters.values()
        )
        assert depends_on_verified_email, f"{route.path} {route.methods} does not depend on require_verified_email"


def test_mutating_ai_routes_require_csrf():
    mutating = [r for r in ai_router.routes if r.methods & {"POST", "DELETE"}]
    assert len(mutating) == 2
    for route in mutating:
        explicit_deps = [d.dependency for d in route.dependencies]
        assert require_csrf in explicit_deps, f"{route.path} {route.methods} does not require CSRF"


def test_status_route_is_not_mutating_and_has_no_csrf_requirement():
    """Confirms GET /ai/status wasn't accidentally left requiring a CSRF
    token, which would just be a needless client-side friction bug, not a
    security gap — but pinning it avoids the opposite drift too (a future
    edit accidentally turning /status into a mutating route without adding
    CSRF back)."""
    status_route = next(r for r in ai_router.routes if r.path.endswith("/status"))
    assert status_route.methods == {"GET"}
    assert [d.dependency for d in status_route.dependencies] == []


def test_router_is_mounted_under_ai_prefix():
    paths = {route.path for route in ai_router.routes}
    assert paths == {"/ai/connect", "/ai/status"}
    assert all(p.startswith("/ai/") for p in paths)


# ---------------------------------------------------------------------------
# Integration-level behavior needing a real DB row + real session cookie —
# written per this repo's own established convention (test_portfolio_
# integration.py / test_research_integration.py): real assertions, marked
# skip because no PostgreSQL/Redis is reachable from this session. Uses the
# real conftest.py fixtures (`client`, `db_session`, `existing_user`) plus
# small local helpers, not a new fixture framework.
# ---------------------------------------------------------------------------

async def _login_headers(client, user) -> dict:
    """Logs a conftest-created `_RegisteredUser` in for real via the actual
    /auth/login endpoint, matching this repo's stated preference for
    exercising real code paths over hand-built sessions."""
    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": user.raw_password})
    assert resp.status_code == 200
    csrf = resp.cookies.get("csrf_token")
    return {"X-CSRF-Token": csrf} if csrf else {}


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_persists_ciphertext_not_plaintext(client, db_session, existing_user):
    headers = await _login_headers(client, existing_user)
    resp = await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-plaintext-secret"}, headers=headers)
    assert resp.status_code == 200
    row = (await db_session.execute(
        select(AIConnection).where(AIConnection.user_id == existing_user.id)
    )).scalar_one()
    assert row.encrypted_api_key != "sk-ant-plaintext-secret"
    assert "sk-ant-plaintext-secret" not in row.encrypted_api_key
    assert decrypt_secret(row.encrypted_api_key) == "sk-ant-plaintext-secret"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_response_never_includes_the_raw_key(client, existing_user):
    headers = await _login_headers(client, existing_user)
    resp = await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-plaintext-secret"}, headers=headers)
    assert "sk-ant-plaintext-secret" not in resp.text
    assert "api_key" not in resp.json()
    assert "encrypted_api_key" not in resp.json()


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_status_returns_safe_metadata_only(client, existing_user):
    headers = await _login_headers(client, existing_user)
    await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-plaintext-secret"}, headers=headers)
    resp = await client.get("/api/v1/ai/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["provider"] == "anthropic"
    assert set(body.keys()) == {"connected", "provider", "connected_at"}
    assert "sk-ant-plaintext-secret" not in resp.text


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_reconnect_replaces_encrypted_key_on_same_row(client, db_session, existing_user):
    headers = await _login_headers(client, existing_user)
    await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-first-key"}, headers=headers)
    await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-second-key"}, headers=headers)
    rows = (await db_session.execute(
        select(AIConnection).where(AIConnection.user_id == existing_user.id)
    )).scalars().all()
    assert len(rows) == 1  # UNIQUE(user_id, provider) — update, not a second row
    assert decrypt_secret(rows[0].encrypted_api_key) == "sk-ant-second-key"


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_disconnect_removes_the_connection(client, db_session, existing_user):
    headers = await _login_headers(client, existing_user)
    await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-first-key"}, headers=headers)
    resp = await client.delete("/api/v1/ai/connect", headers=headers)
    assert resp.status_code == 204
    status_resp = await client.get("/api/v1/ai/status", headers=headers)
    assert status_resp.json()["connected"] is False


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_unauthenticated_rejected(client):
    resp = await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-x"})
    assert resp.status_code == 401


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_status_unauthenticated_rejected(client):
    resp = await client.get("/api/v1/ai/status")
    assert resp.status_code == 401


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_disconnect_unauthenticated_rejected(client):
    resp = await client.delete("/api/v1/ai/connect")
    assert resp.status_code == 401


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_user_a_cannot_see_user_bs_connection(client, existing_user, target_user):
    """`target_user` (conftest.py) is a second independently-registered user
    — reused here purely as "a second real member", same as its docstring
    already invites for reset-flow tests."""
    b_headers = await _login_headers(client, target_user)
    await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-user-b-key"}, headers=b_headers)

    a_headers = await _login_headers(client, existing_user)
    resp = await client.get("/api/v1/ai/status", headers=a_headers)
    assert resp.status_code == 200
    assert resp.json()["connected"] is False  # user A has no connection of their own — never user B's


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_user_a_disconnect_does_not_affect_user_bs_connection(client, db_session, existing_user, target_user):
    b_headers = await _login_headers(client, target_user)
    await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-user-b-key"}, headers=b_headers)

    a_headers = await _login_headers(client, existing_user)
    await client.delete("/api/v1/ai/connect", headers=a_headers)  # no-op for A, no connection exists

    b_status = await client.get("/api/v1/ai/status", headers=b_headers)
    assert b_status.json()["connected"] is True  # untouched


@pytest.mark.skip(reason="requires a real PostgreSQL test database — not available in this environment")
async def test_connect_fails_safely_with_503_when_encryption_not_configured(client, existing_user, unconfigured_encryption_secret):
    """API-level version of test_encrypt_raises_cleanly_when_secret_
    unconfigured — confirms the router/service layer turns
    EncryptionNotConfiguredError into a clean 503, never a raw 500 and
    never a silent plaintext-storage fallback."""
    headers = await _login_headers(client, existing_user)
    resp = await client.post("/api/v1/ai/connect", json={"provider": "anthropic", "api_key": "sk-ant-x"}, headers=headers)
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "AI_ENCRYPTION_NOT_CONFIGURED"
