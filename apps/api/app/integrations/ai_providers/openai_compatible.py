"""OpenAI-compatible chat provider (`openai_compatible`).

Provider-neutral on purpose: the endpoint may front Ollama, vLLM, LM Studio,
LiteLLM or any gateway implementing the OpenAI HTTP contract. Nothing here
hardcodes an endpoint or a model — both come from the user's saved
`ai_connections` row.

CONTRACT
- `endpoint` is the BASE url ending in the API root (e.g. `http://host:4451/v1`).
  Requests are built as `{endpoint}/models` and `{endpoint}/chat/completions`.
- `normalize_endpoint()` is the one canonical rule: trims whitespace and
  trailing slashes, rejects credentials/query/fragment, and REJECTS an endpoint
  that already ends in `/chat/completions`, `/completions` or `/models` (rather
  than saving something that would later produce `/chat/completions/chat/
  completions`). It never appends `/v1` on its own.

SECURITY
- The API key is a per-call argument. It is never stored on the adapter,
  never logged, and never placed in any exception message: every error string
  below is a fixed literal.
- SERVER-SIDE REQUEST FORGERY: this module makes outbound requests to a
  user-supplied URL. `validate_endpoint_target()` resolves the host and refuses
  anything that is not a globally-routable address (loopback, RFC1918 private,
  link-local incl. cloud metadata 169.254.169.254, reserved, CGNAT). Redirects
  are never followed, response bodies are size-capped, and timeouts are short.
  KNOWN RESIDUAL RISK: the check resolves DNS separately from httpx's own
  connection, so a hostile DNS server could in principle answer differently
  (DNS rebinding). Mitigate at the network layer (egress firewall) in
  production. Self-hosters who legitimately need a LAN endpoint can set
  QFINERA_ALLOW_PRIVATE_AI_ENDPOINTS=1; leave it unset on any shared deployment.
"""
import asyncio
import ipaddress
import json
import logging
import os
import socket
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.integrations.ai_providers.base import AiProviderError

logger = logging.getLogger("qfinera.ai.openai_compatible")

CONNECT_TIMEOUT_SECONDS = 5.0
DISCOVERY_READ_TIMEOUT_SECONDS = 10.0
CHAT_READ_TIMEOUT_SECONDS = 90.0
MAX_MODELS_RESPONSE_BYTES = 1_000_000
MAX_CHAT_RESPONSE_BYTES = 2_000_000
MAX_ENDPOINT_LENGTH = 2048
MAX_MODEL_IDS = 200
MAX_MODEL_ID_LENGTH = 200

_FORBIDDEN_TAILS = ("/chat/completions", "/completions", "/models")
_ALLOW_PRIVATE_ENV = "QFINERA_ALLOW_PRIVATE_AI_ENDPOINTS"


class InvalidEndpointError(ValueError):
    """The endpoint the user typed is unusable. The message is safe to show."""


class AuthenticationFailed(AiProviderError):
    """The endpoint rejected the API key (HTTP 401/403)."""


class EndpointUnreachable(AiProviderError):
    """DNS/connect/timeout failure reaching the endpoint."""


class InvalidProviderResponse(AiProviderError):
    """The endpoint answered, but not in the OpenAI-compatible shape."""


def normalize_endpoint(raw: str) -> str:
    """Canonical base-URL form. Idempotent: normalize(normalize(x)) == normalize(x)."""
    value = (raw or "").strip()
    if not value:
        raise InvalidEndpointError("Enter the AI endpoint URL.")
    if len(value) > MAX_ENDPOINT_LENGTH:
        raise InvalidEndpointError("The endpoint URL is too long.")
    try:
        parts = urlsplit(value)
        _ = parts.port  # raises ValueError on a malformed port
    except ValueError as e:
        raise InvalidEndpointError("The endpoint URL is not valid.") from e
    if parts.scheme.lower() not in ("http", "https"):
        raise InvalidEndpointError("The endpoint must start with http:// or https://.")
    if not parts.hostname:
        raise InvalidEndpointError("The endpoint URL is missing a host.")
    if parts.username is not None or parts.password is not None:
        raise InvalidEndpointError("Do not put credentials in the endpoint URL. Use the API key field.")
    if parts.query or parts.fragment:
        raise InvalidEndpointError("The endpoint URL must not contain a query string or fragment.")
    path = parts.path.rstrip("/")
    lowered = path.lower()
    if any(lowered.endswith(tail) for tail in _FORBIDDEN_TAILS):
        raise InvalidEndpointError(
            "Enter the base API URL (for example http://host:4451/v1), not the /chat/completions or /models URL."
        )
    return urlunsplit((parts.scheme.lower(), parts.netloc, path, "", ""))


def _private_endpoints_allowed() -> bool:
    return os.environ.get(_ALLOW_PRIVATE_ENV, "").strip() == "1"


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global


async def validate_endpoint_target(endpoint: str) -> None:
    """Refuse endpoints that resolve to non-public addresses (SSRF guard).
    Raises InvalidEndpointError for a forbidden target, EndpointUnreachable if
    the host cannot be resolved at all."""
    if _private_endpoints_allowed():
        return
    parts = urlsplit(endpoint)
    host = parts.hostname or ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise EndpointUnreachable("Unable to reach AI endpoint.") from e
    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public(a) for a in addresses):
        raise InvalidEndpointError(
            "That endpoint points at a private or reserved network address, which isn't allowed."
        )


async def _read_capped(response: httpx.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise InvalidProviderResponse("The AI endpoint returned too much data.")
        chunks.append(chunk)
    return b"".join(chunks)


class OpenAICompatibleProvider:
    """Implements `AiProvider` (see base.py) for any OpenAI-compatible gateway,
    plus `list_models()` for discovery. `endpoint` must already be normalized."""

    def __init__(self, endpoint: str, model: str | None = None, *, transport: httpx.AsyncBaseTransport | None = None):
        self.endpoint = endpoint
        self.model = model
        self._transport = transport  # tests inject httpx.MockTransport here; never used in production

    def _client(self, read_timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(read_timeout, connect=CONNECT_TIMEOUT_SECONDS),
            follow_redirects=False,
            trust_env=False,
            transport=self._transport,
        )

    async def _request(self, method: str, path: str, *, api_key: str, read_timeout: float, limit: int,
                       payload: dict | None = None) -> dict:
        url = f"{self.endpoint}{path}"
        headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        try:
            async with self._client(read_timeout) as client:
                async with client.stream(method, url, headers=headers, json=payload) as response:
                    status = response.status_code
                    body = await _read_capped(response, limit) if status < 300 else b""
        except httpx.HTTPError as e:
            # Log only the exception TYPE — httpx messages can embed the URL.
            logger.warning("OpenAI-compatible request failed: %s", type(e).__name__)
            raise EndpointUnreachable("Unable to reach AI endpoint.") from e

        if status in (401, 403):
            raise AuthenticationFailed("Authentication failed.")
        if 300 <= status < 400:
            raise InvalidProviderResponse("The endpoint redirected the request. Use its final URL instead.")
        if status == 404:
            raise InvalidProviderResponse(
                "The endpoint didn't recognise this request. Check that the URL is the base API URL (usually ending in /v1)."
            )
        if status == 429:
            raise AiProviderError("The AI endpoint is rate-limiting requests. Please try again shortly.")
        if status >= 400:
            raise AiProviderError(f"The AI endpoint returned an error (status {status}).")
        try:
            data = json.loads(body)
        except ValueError as e:
            raise InvalidProviderResponse("The AI endpoint returned an unexpected response.") from e
        if not isinstance(data, dict):
            raise InvalidProviderResponse("The AI endpoint returned an unexpected response.")
        return data

    async def list_models(self, *, api_key: str) -> list[str]:
        """GET {endpoint}/models -> validated, de-duplicated, bounded model IDs."""
        data = await self._request(
            "GET", "/models", api_key=api_key,
            read_timeout=DISCOVERY_READ_TIMEOUT_SECONDS, limit=MAX_MODELS_RESPONSE_BYTES,
        )
        items = data.get("data")
        if not isinstance(items, list):
            raise InvalidProviderResponse("The AI endpoint returned an unexpected model list.")
        ids: list[str] = []
        for item in items:
            model_id = item.get("id") if isinstance(item, dict) else None
            if isinstance(model_id, str) and 0 < len(model_id) <= MAX_MODEL_ID_LENGTH and model_id not in ids:
                ids.append(model_id)
            if len(ids) >= MAX_MODEL_IDS:
                break
        return ids

    async def ask(self, *, api_key: str, system_prompt: str, question: str) -> str:
        """POST {endpoint}/chat/completions using the model from the saved connection."""
        if not self.model:
            raise AiProviderError("No model is selected for this AI connection.")
        data = await self._request(
            "POST", "/chat/completions", api_key=api_key,
            read_timeout=CHAT_READ_TIMEOUT_SECONDS, limit=MAX_CHAT_RESPONSE_BYTES,
            payload={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise InvalidProviderResponse("The AI endpoint returned an unexpected response.") from e
        if not isinstance(content, str):
            raise InvalidProviderResponse("The AI endpoint returned an unexpected response.")
        return content
