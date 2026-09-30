"""OpenAI-Compatible AI provider — endpoint normalization, SSRF guard, adapter
(model discovery + chat completion), Test Connection, saved-connection
handling, provider resolution, and secret hygiene.

ALL upstream HTTP is mocked with httpx.MockTransport — nothing here touches the
network or any real AI server. The endpoint used is a literal PUBLIC IP
(8.8.8.8) purely so the SSRF guard (which requires a globally-routable address)
passes without any DNS lookup; no request is ever actually sent to it.

Real fixtures only (db_session / client / existing_user / target_user): every
test runs inside conftest's rolled-back transaction, Redis DB 15 is flushed per
test (so the Test Connection rate-limit counter starts at zero each test).

Style note: the service function is `check_connection` (not `test_connection`)
so pytest can never mistake it for a test if it's imported by name.
"""
import inspect
import logging
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import func, select

from app.core import crypto
from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.core.errors import QFinanceAPIError
from app.integrations.ai_providers import openai_compatible as oc
from app.integrations.ai_providers.base import AiProviderError
from app.integrations.ai_providers.openai_compatible import (
    AuthenticationFailed, EndpointUnreachable, InvalidEndpointError, InvalidProviderResponse,
    OpenAICompatibleProvider, normalize_endpoint, validate_endpoint_target,
)
from app.modules.ai import service as ai_service
from app.modules.ai.models import AIConnection

settings = get_settings()

KEY = "sk-test-SECRET-value-must-never-leak-9f3a"
WRONG_KEY = "sk-wrong-KEY-value-must-never-leak-77b1"
ENDPOINT = "http://8.8.8.8:4451/v1"


@pytest.fixture
def configured_encryption_secret(monkeypatch):
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", "test-only-secret-do-not-reuse")


def _upstream(models=("qwen3-8b", "gpt-fast"), key=KEY, calls=None):
    """A fake OpenAI-compatible server: valid only for `key`; serves /models."""
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        if request.headers.get("authorization") != f"Bearer {key}":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(200, json={"object": "list", "data": [{"id": m} for m in models]})
        return httpx.Response(404, json={"error": "not found"})
    return handler


def _install_upstream(monkeypatch, handler):
    """Make the SERVICE build its provider on a MockTransport."""
    real = OpenAICompatibleProvider
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        ai_service, "OpenAICompatibleProvider",
        lambda endpoint, model=None: real(endpoint, model, transport=transport),
    )


def _provider(handler, endpoint=ENDPOINT, model="qwen3-8b") -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(endpoint, model, transport=httpx.MockTransport(handler))


async def _login(client, db_session, user, *, verified=True) -> dict:
    if verified:
        user.user.email_verified_at = datetime.now(timezone.utc)
        await db_session.flush()
    resp = await client.post("/api/v1/auth/login", json={"email": user.email, "password": user.raw_password})
    assert resp.status_code == 200, resp.text
    return {"X-CSRF-Token": client.cookies.get(settings.CSRF_COOKIE_NAME)}


def _connect_body(**over):
    body = {"provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT, "model": "qwen3-8b"}
    body.update(over)
    return body


# ===========================================================================
# 1-2. Provider recognised / endpoint normalization (pure)
# ===========================================================================

def test_openai_compatible_is_a_recognised_provider():
    from app.modules.ai.models import PROVIDER_OPENAI_COMPATIBLE, VALID_PROVIDERS
    assert PROVIDER_OPENAI_COMPATIBLE == "openai_compatible"
    assert "openai_compatible" in VALID_PROVIDERS
    assert "ollama" not in VALID_PROVIDERS  # provider-neutral by design


@pytest.mark.parametrize("raw,expected", [
    ("http://122.15.146.241:4451/v1", "http://122.15.146.241:4451/v1"),
    ("http://122.15.146.241:4451/v1/", "http://122.15.146.241:4451/v1"),
    ("  http://122.15.146.241:4451/v1//  ", "http://122.15.146.241:4451/v1"),
    ("https://gateway.example.com/openai/api/v1", "https://gateway.example.com/openai/api/v1"),  # custom base path kept
    ("http://localhost:11434", "http://localhost:11434"),  # NEVER silently appends /v1
    ("HTTP://Example.com/v1", "http://Example.com/v1"),
])
def test_normalize_endpoint_canonical_forms(raw, expected):
    assert normalize_endpoint(raw) == expected
    assert normalize_endpoint(expected) == expected  # idempotent


@pytest.mark.parametrize("raw", [
    "", "   ", "not a url", "ftp://host/v1", "http:///v1",
    "http://user:pw@host/v1", "http://host/v1?x=1", "http://host/v1#frag",
    "http://host/v1/chat/completions", "http://host/v1/chat/completions/",
    "http://host/v1/completions", "http://host/v1/models", "http://host:99999/v1",
])
def test_normalize_endpoint_rejects_unusable_input(raw):
    with pytest.raises(InvalidEndpointError):
        normalize_endpoint(raw)


def test_endpoint_rejection_messages_never_echo_embedded_credentials():
    with pytest.raises(InvalidEndpointError) as exc:
        normalize_endpoint("http://admin:hunter2@host/v1")
    assert "hunter2" not in str(exc.value)


async def test_request_urls_are_built_without_duplicated_path_segments():
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url)))
        if request.method == "POST":
            return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    p = _provider(handler, endpoint=normalize_endpoint("http://8.8.8.8:4451/v1/"))
    await p.list_models(api_key=KEY)
    await p.ask(api_key=KEY, system_prompt="s", question="q")
    assert seen == [("GET", "http://8.8.8.8:4451/v1/models"), ("POST", "http://8.8.8.8:4451/v1/chat/completions")]


# ===========================================================================
# 12. SSRF guard
# ===========================================================================

@pytest.mark.parametrize("endpoint", [
    "http://127.0.0.1:11434/v1", "http://10.0.0.5/v1", "http://192.168.1.10:8000/v1",
    "http://172.16.0.1/v1", "http://169.254.169.254/latest/meta-data", "http://100.64.0.1/v1",
    "http://0.0.0.0/v1",
])
async def test_private_and_reserved_targets_are_refused(endpoint, monkeypatch):
    monkeypatch.delenv("QFINERA_ALLOW_PRIVATE_AI_ENDPOINTS", raising=False)
    with pytest.raises(InvalidEndpointError):
        await validate_endpoint_target(normalize_endpoint(endpoint))


async def test_public_ip_target_is_allowed(monkeypatch):
    monkeypatch.delenv("QFINERA_ALLOW_PRIVATE_AI_ENDPOINTS", raising=False)
    await validate_endpoint_target(ENDPOINT)  # no exception


async def test_private_targets_allowed_only_with_explicit_operator_opt_in(monkeypatch):
    monkeypatch.setenv("QFINERA_ALLOW_PRIVATE_AI_ENDPOINTS", "1")
    await validate_endpoint_target("http://127.0.0.1:11434/v1")


# ===========================================================================
# 5-6, 8-11. Adapter: model discovery, auth failure, chat completion
# ===========================================================================

async def test_model_discovery_sends_bearer_key_and_parses_ids():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["method"] = request.method
        return httpx.Response(200, json={"object": "list", "data": [
            {"id": "qwen3-8b"}, {"id": "gpt-fast"}, {"id": "qwen3-8b"},  # duplicate
            {"id": ""}, {"nope": 1}, "junk", {"id": 5},                  # all ignored
            {"id": "dots.ocr-Q8_0"}, {"id": "qwen3:14b"},
        ]})

    models = await _provider(handler).list_models(api_key=KEY)
    assert seen == {"auth": f"Bearer {KEY}", "method": "GET"}
    assert models == ["qwen3-8b", "gpt-fast", "dots.ocr-Q8_0", "qwen3:14b"]


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_failure_is_typed_and_key_free(status):
    with pytest.raises(AuthenticationFailed) as exc:
        await _provider(lambda r: httpx.Response(status, json={"error": f"bad {KEY}"})).list_models(api_key=KEY)
    assert KEY not in str(exc.value)  # upstream body is never propagated


@pytest.mark.parametrize("make_response,exc_type", [
    (lambda r: httpx.Response(404), InvalidProviderResponse),
    (lambda r: httpx.Response(200, content=b"not json"), InvalidProviderResponse),
    (lambda r: httpx.Response(200, json=[1, 2]), InvalidProviderResponse),
    (lambda r: httpx.Response(200, json={"data": "nope"}), InvalidProviderResponse),
    (lambda r: httpx.Response(500, json={"error": "boom"}), AiProviderError),
    (lambda r: httpx.Response(429), AiProviderError),
])
async def test_bad_upstream_responses_raise_safe_provider_errors(make_response, exc_type):
    with pytest.raises(exc_type):
        await _provider(make_response).list_models(api_key=KEY)


async def test_redirects_are_not_followed():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    with pytest.raises(InvalidProviderResponse):
        await _provider(handler).list_models(api_key=KEY)
    assert calls == [f"{ENDPOINT}/models"]  # the redirect target was never requested


async def test_oversized_response_is_rejected(monkeypatch):
    monkeypatch.setattr(oc, "MAX_MODELS_RESPONSE_BYTES", 16)
    with pytest.raises(InvalidProviderResponse):
        await _provider(lambda r: httpx.Response(200, json={"data": [{"id": "x" * 100}]})).list_models(api_key=KEY)


async def test_network_failure_maps_to_unreachable_without_leaking_key_or_logging_it(caplog):
    def handler(request):
        raise httpx.ConnectError(f"connection failed for Bearer {KEY}")  # hostile: exception text contains the key

    caplog.set_level(logging.DEBUG)
    with pytest.raises(EndpointUnreachable) as exc:
        await _provider(handler).list_models(api_key=KEY)
    assert KEY not in str(exc.value)
    assert KEY not in caplog.text


async def test_chat_completion_posts_to_chat_completions_with_saved_model():
    seen = {}

    def handler(request):
        import json
        seen.update(method=request.method, url=str(request.url), auth=request.headers.get("authorization"),
                    body=json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "an answer"}}]})

    answer = await _provider(handler, model="some-other-model:7b").ask(
        api_key=KEY, system_prompt="be careful", question="what is X?")
    assert answer == "an answer"
    assert seen["method"] == "POST"
    assert seen["url"] == f"{ENDPOINT}/chat/completions"
    assert seen["auth"] == f"Bearer {KEY}"
    assert seen["body"]["model"] == "some-other-model:7b"  # from the connection, not hardcoded
    assert [m["role"] for m in seen["body"]["messages"]] == ["system", "user"]


async def test_chat_without_a_saved_model_or_with_malformed_reply_fails_cleanly():
    with pytest.raises(AiProviderError):
        await _provider(lambda r: httpx.Response(200, json={}), model=None).ask(api_key=KEY, system_prompt="s", question="q")
    with pytest.raises(InvalidProviderResponse):
        await _provider(lambda r: httpx.Response(200, json={"choices": []})).ask(api_key=KEY, system_prompt="s", question="q")


def test_adapter_source_hardcodes_neither_the_model_nor_the_endpoint():
    src = inspect.getsource(oc)
    assert "qwen3-8b" not in src
    assert "122.15.146.241" not in src


# ===========================================================================
# 3-4. Saved connection: encrypted at rest, never returned (API level)
# ===========================================================================

async def test_connect_encrypts_key_normalizes_endpoint_and_never_returns_the_key(
    client, db_session, existing_user, configured_encryption_secret,
):
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/connect", json=_connect_body(endpoint=ENDPOINT + "/"), headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["connected"], body["provider"], body["endpoint"], body["model"]) == (
        True, "openai_compatible", ENDPOINT, "qwen3-8b")
    assert KEY not in resp.text
    assert not {"api_key", "encrypted_api_key"} & set(body)

    row = (await db_session.execute(select(AIConnection).where(AIConnection.user_id == existing_user.id))).scalar_one()
    assert row.encrypted_api_key != KEY and KEY not in row.encrypted_api_key
    assert decrypt_secret(row.encrypted_api_key) == KEY
    assert (row.endpoint, row.model) == (ENDPOINT, "qwen3-8b")


async def test_status_and_connections_return_safe_metadata_only(
    client, db_session, existing_user, configured_encryption_secret,
):
    headers = await _login(client, db_session, existing_user)
    await client.post("/api/v1/ai/connect", json=_connect_body(), headers=headers)

    status = await client.get("/api/v1/ai/status?provider=openai_compatible")
    assert status.status_code == 200
    assert (status.json()["endpoint"], status.json()["model"]) == (ENDPOINT, "qwen3-8b")
    assert KEY not in status.text

    listing = await client.get("/api/v1/ai/connections")
    assert listing.status_code == 200
    assert [c["provider"] for c in listing.json()] == ["openai_compatible"]
    assert KEY not in listing.text


async def test_reconnect_updates_the_same_row_and_disconnect_removes_it(
    client, db_session, existing_user, configured_encryption_secret,
):
    headers = await _login(client, db_session, existing_user)
    await client.post("/api/v1/ai/connect", json=_connect_body(model="qwen3-8b"), headers=headers)
    r2 = await client.post("/api/v1/ai/connect", json=_connect_body(api_key="sk-second-key", model="qwen3:14b"), headers=headers)
    assert r2.status_code == 200 and r2.json()["model"] == "qwen3:14b"

    count = (await db_session.execute(select(func.count()).select_from(AIConnection)
             .where(AIConnection.user_id == existing_user.id))).scalar_one()
    assert count == 1
    row = (await db_session.execute(select(AIConnection).where(AIConnection.user_id == existing_user.id))).scalar_one()
    assert decrypt_secret(row.encrypted_api_key) == "sk-second-key"

    assert (await client.delete("/api/v1/ai/connect?provider=openai_compatible", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/ai/status?provider=openai_compatible")).json()["connected"] is False


@pytest.mark.parametrize("over,expected_code", [
    ({"endpoint": None}, "INVALID_AI_ENDPOINT"),
    ({"endpoint": "http://8.8.8.8:4451/v1/chat/completions"}, "INVALID_AI_ENDPOINT"),
    ({"endpoint": "http://127.0.0.1:11434/v1"}, "INVALID_AI_ENDPOINT"),  # SSRF guard also applies at SAVE time
    ({"model": None}, "VALIDATION_ERROR"),
    ({"model": "has space"}, "VALIDATION_ERROR"),
    ({"api_key": "   "}, "VALIDATION_ERROR"),
])
async def test_connect_rejects_invalid_openai_compatible_input(
    over, expected_code, client, db_session, existing_user, configured_encryption_secret,
):
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/connect", json=_connect_body(**over), headers=headers)
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == expected_code
    assert KEY not in resp.text


async def test_endpoint_and_model_are_rejected_for_other_providers(
    client, db_session, existing_user, configured_encryption_secret,
):
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/connect", json={
        "provider": "anthropic", "api_key": KEY, "endpoint": ENDPOINT, "model": "x"}, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
async def test_existing_providers_still_connect_and_have_no_endpoint_or_model(
    provider, client, db_session, existing_user, configured_encryption_secret,
):
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/connect", json={"provider": provider, "api_key": KEY}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert (resp.json()["provider"], resp.json()["endpoint"], resp.json()["model"]) == (provider, None, None)
    assert KEY not in resp.text
    row = (await db_session.execute(select(AIConnection).where(
        AIConnection.user_id == existing_user.id, AIConnection.provider == provider))).scalar_one()
    assert decrypt_secret(row.encrypted_api_key) == KEY


async def test_connect_fails_with_503_when_encryption_is_not_configured(client, db_session, existing_user, monkeypatch):
    monkeypatch.setattr(crypto.settings, "AI_KEY_ENCRYPTION_SECRET", None)
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/connect", json=_connect_body(), headers=headers)
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "AI_ENCRYPTION_NOT_CONFIGURED"
    count = (await db_session.execute(select(func.count()).select_from(AIConnection))).scalar_one()
    assert count == (await db_session.execute(select(func.count()).select_from(AIConnection)
                     .where(AIConnection.user_id != existing_user.id))).scalar_one()  # nothing stored for this user


# ---- access control ------------------------------------------------------

async def test_ai_endpoints_require_authentication_csrf_and_verified_email(
    client, db_session, existing_user, configured_encryption_secret,
):
    assert (await client.get("/api/v1/ai/connections")).status_code == 401
    assert (await client.get("/api/v1/ai/status?provider=openai_compatible")).status_code == 401

    headers = await _login(client, db_session, existing_user)
    no_csrf = await client.post("/api/v1/ai/connect", json=_connect_body())  # cookies present, header missing
    assert no_csrf.status_code == 403 and no_csrf.json()["error"]["code"] == "CSRF_MISMATCH"
    no_csrf_test = await client.post("/api/v1/ai/test-connection", json={"provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT})
    assert no_csrf_test.status_code == 403 and no_csrf_test.json()["error"]["code"] == "CSRF_MISMATCH"
    assert headers  # (login succeeded; the header is deliberately withheld above)


async def test_unverified_email_cannot_use_ai_connections(client, db_session, existing_user, configured_encryption_secret):
    headers = await _login(client, db_session, existing_user, verified=False)
    resp = await client.post("/api/v1/ai/connect", json=_connect_body(), headers=headers)
    assert resp.status_code in (401, 403)
    assert (await client.get("/api/v1/ai/connections")).status_code in (401, 403)


async def test_one_users_connections_are_invisible_to_another(
    client, db_session, existing_user, target_user, configured_encryption_secret,
):
    a = await _login(client, db_session, existing_user)
    await client.post("/api/v1/ai/connect", json=_connect_body(), headers=a)
    await _login(client, db_session, target_user)  # same client jar is now user B
    assert (await client.get("/api/v1/ai/connections")).json() == []
    assert (await client.get("/api/v1/ai/status?provider=openai_compatible")).json()["connected"] is False


# ===========================================================================
# 7-9. Test Connection
# ===========================================================================

async def test_test_connection_success_lists_models_and_confirms_selected_model(
    client, db_session, existing_user, monkeypatch,
):
    calls = []
    _install_upstream(monkeypatch, _upstream(calls=calls))
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/test-connection", json={
        "provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT + "/", "model": "qwen3-8b"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True and body["status"] == "connected"
    assert body["model_count"] == 2 and body["models"] == ["qwen3-8b", "gpt-fast"]
    assert (body["selected_model"], body["selected_model_found"]) == ("qwen3-8b", True)
    assert body["message"].startswith("Connected")
    assert "http://" in body["warning"]  # plain-http advisory
    assert KEY not in resp.text
    assert len(calls) == 1 and str(calls[0].url) == f"{ENDPOINT}/models"
    assert calls[0].headers["authorization"] == f"Bearer {KEY}"


async def test_test_connection_reports_missing_selected_model(client, db_session, existing_user, monkeypatch):
    _install_upstream(monkeypatch, _upstream())
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/test-connection", json={
        "provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT, "model": "xyz"}, headers=headers)
    body = resp.json()
    assert body["ok"] is True and body["selected_model_found"] is False
    assert 'Selected model "xyz" was not found.' in body["message"]


async def test_test_connection_auth_failure_is_reported_safely(client, db_session, existing_user, monkeypatch):
    _install_upstream(monkeypatch, _upstream())  # server only accepts KEY
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/test-connection", json={
        "provider": "openai_compatible", "api_key": WRONG_KEY, "endpoint": ENDPOINT}, headers=headers)
    body = resp.json()
    assert resp.status_code == 200
    assert (body["ok"], body["status"], body["message"]) == (False, "auth_failed", "Authentication failed.")
    assert WRONG_KEY not in resp.text


async def test_test_connection_unreachable_and_malformed_upstreams(client, db_session, existing_user, monkeypatch, caplog):
    headers = await _login(client, db_session, existing_user)
    caplog.set_level(logging.DEBUG)

    def boom(request):
        raise httpx.ConnectError(f"cannot connect, Authorization: Bearer {KEY}")

    _install_upstream(monkeypatch, boom)
    r1 = await client.post("/api/v1/ai/test-connection", json={
        "provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT}, headers=headers)
    assert (r1.json()["ok"], r1.json()["status"], r1.json()["message"]) == (False, "unreachable", "Unable to reach AI endpoint.")

    _install_upstream(monkeypatch, lambda r: httpx.Response(200, json={"data": "nope"}))
    r2 = await client.post("/api/v1/ai/test-connection", json={
        "provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT}, headers=headers)
    assert (r2.json()["ok"], r2.json()["status"]) == (False, "invalid_response")

    for text in (r1.text, r2.text, caplog.text):
        assert KEY not in text  # never in a response, never in a log


async def test_test_connection_refuses_bad_and_private_targets_without_calling_out(client, db_session, existing_user, monkeypatch):
    calls = []
    _install_upstream(monkeypatch, _upstream(calls=calls))
    headers = await _login(client, db_session, existing_user)
    for endpoint in ("http://127.0.0.1:11434/v1", "http://169.254.169.254/latest", ENDPOINT + "/chat/completions"):
        resp = await client.post("/api/v1/ai/test-connection", json={
            "provider": "openai_compatible", "api_key": KEY, "endpoint": endpoint}, headers=headers)
        assert resp.status_code == 400 and resp.json()["error"]["code"] == "INVALID_AI_ENDPOINT"
    assert calls == []


async def test_test_connection_is_only_for_openai_compatible(client, db_session, existing_user):
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/test-connection", json={"provider": "anthropic", "api_key": KEY}, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "AI_TEST_NOT_SUPPORTED"


async def test_test_connection_can_use_the_saved_key_but_never_against_a_different_endpoint(
    client, db_session, existing_user, monkeypatch, configured_encryption_secret,
):
    calls = []
    _install_upstream(monkeypatch, _upstream(calls=calls))
    headers = await _login(client, db_session, existing_user)
    assert (await client.post("/api/v1/ai/connect", json=_connect_body(), headers=headers)).status_code == 200

    ok = await client.post("/api/v1/ai/test-connection", json={"provider": "openai_compatible"}, headers=headers)
    assert ok.json()["ok"] is True and ok.json()["selected_model"] == "qwen3-8b"  # saved key AND saved model used
    assert calls[-1].headers["authorization"] == f"Bearer {KEY}"
    n = len(calls)

    other = await client.post("/api/v1/ai/test-connection", json={
        "provider": "openai_compatible", "endpoint": "http://1.1.1.1:9999/v1"}, headers=headers)
    assert other.status_code == 400
    assert len(calls) == n  # the saved key was NOT sent to the different endpoint
    assert KEY not in other.text


async def test_test_connection_without_key_or_saved_connection_asks_for_a_key(client, db_session, existing_user):
    headers = await _login(client, db_session, existing_user)
    resp = await client.post("/api/v1/ai/test-connection", json={"provider": "openai_compatible", "endpoint": ENDPOINT}, headers=headers)
    assert resp.status_code == 400 and resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_test_connection_is_rate_limited_per_user(client, db_session, existing_user, monkeypatch):
    _install_upstream(monkeypatch, _upstream())
    headers = await _login(client, db_session, existing_user)
    payload = {"provider": "openai_compatible", "api_key": KEY, "endpoint": ENDPOINT}
    codes = [(await client.post("/api/v1/ai/test-connection", json=payload, headers=headers)).status_code
             for _ in range(ai_service.TEST_CONNECTION_LIMIT + 1)]
    assert codes[:-1] == [200] * ai_service.TEST_CONNECTION_LIMIT
    assert codes[-1] == 429


# ===========================================================================
# Research integration: connection -> provider -> endpoint -> model
# ===========================================================================

async def test_resolve_provider_uses_the_saved_connection(db_session, existing_user, configured_encryption_secret):
    await ai_service.connect(db_session, user_id=existing_user.id, provider="openai_compatible",
                             api_key=KEY, endpoint=ENDPOINT, model="custom-model-7b")
    adapter, key, conn = await ai_service.resolve_provider_for_user(db_session, user_id=existing_user.id)
    assert isinstance(adapter, OpenAICompatibleProvider)
    assert (adapter.endpoint, adapter.model, key, conn.provider) == (ENDPOINT, "custom-model-7b", KEY, "openai_compatible")

    # ...and a chat through the resolved adapter posts to the saved endpoint with the saved model
    seen = {}

    def handler(request):
        import json
        seen.update(url=str(request.url), model=json.loads(request.content)["model"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    adapter._transport = httpx.MockTransport(handler)
    assert await adapter.ask(api_key=key, system_prompt="s", question="q") == "ok"
    assert seen == {"url": f"{ENDPOINT}/chat/completions", "model": "custom-model-7b"}


async def test_active_connection_is_the_most_recently_connected(db_session, existing_user, configured_encryption_secret):
    await ai_service.connect(db_session, user_id=existing_user.id, provider="openai", api_key="sk-openai-key")
    await ai_service.connect(db_session, user_id=existing_user.id, provider="openai_compatible",
                             api_key=KEY, endpoint=ENDPOINT, model="m")
    listing = await ai_service.list_connections(db_session, user_id=existing_user.id)
    assert [c["provider"] for c in listing] == ["openai_compatible", "openai"]
    _, _, conn = await ai_service.resolve_provider_for_user(db_session, user_id=existing_user.id)
    assert conn.provider == "openai_compatible"


async def test_resolve_provider_errors_are_clean(db_session, existing_user, configured_encryption_secret):
    with pytest.raises(QFinanceAPIError) as none:
        await ai_service.resolve_provider_for_user(db_session, user_id=existing_user.id)
    assert (none.value.code, none.value.status_code) == ("AI_NOT_CONNECTED", 503)

    await ai_service.connect(db_session, user_id=existing_user.id, provider="anthropic", api_key="sk-ant-x")
    with pytest.raises(QFinanceAPIError) as unsupported:
        await ai_service.resolve_provider_for_user(db_session, user_id=existing_user.id)
    assert unsupported.value.code == "AI_PROVIDER_UNSUPPORTED"  # honest: Anthropic isn't behind AiProvider yet


async def test_resolve_provider_refuses_a_saved_endpoint_that_is_no_longer_allowed(
    db_session, existing_user, configured_encryption_secret,
):
    """The SSRF guard is re-applied on EVERY use, not just at save time."""
    await ai_service.connect(db_session, user_id=existing_user.id, provider="openai_compatible",
                             api_key=KEY, endpoint=ENDPOINT, model="m")
    row = (await db_session.execute(select(AIConnection).where(AIConnection.user_id == existing_user.id))).scalar_one()
    row.endpoint = "http://169.254.169.254/latest"  # e.g. DNS later re-pointed / row edited
    await db_session.flush()
    with pytest.raises(QFinanceAPIError) as exc:
        await ai_service.resolve_provider_for_user(db_session, user_id=existing_user.id)
    assert exc.value.code == "INVALID_AI_ENDPOINT"


async def test_research_context_never_carries_credentials():
    """The Research AI context is built from research + company data only; it has
    no field a key/endpoint/token could occupy."""
    from app.modules.research.ai_context import ResearchAIContext
    fields = {f.lower() for f in ResearchAIContext.__dataclass_fields__}
    assert not [f for f in fields if any(s in f for s in ("key", "secret", "token", "password", "credential", "endpoint"))]
