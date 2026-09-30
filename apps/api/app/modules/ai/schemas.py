"""Pydantic schemas — ai module. No field named api_key/key/token appears in
ANY response schema below, on purpose — structurally, not just by
discipline, matching portfolio/schemas.py's precedent. `endpoint` and
`model` (OpenAI-Compatible only) are NOT secrets and may appear in responses;
the API key never does."""
from datetime import datetime

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    provider: str = "anthropic"
    api_key: str = Field(max_length=4096)
    endpoint: str | None = Field(default=None, max_length=2048)  # openai_compatible only
    model: str | None = Field(default=None, max_length=200)  # openai_compatible only


class StatusResponse(BaseModel):
    connected: bool
    provider: str | None
    connected_at: datetime | None
    endpoint: str | None = None
    model: str | None = None


class TestConnectionRequest(BaseModel):
    provider: str
    # If api_key is omitted, the caller's SAVED key for this provider is used
    # (and endpoint, if given, must equal the saved endpoint).
    api_key: str | None = Field(default=None, max_length=4096)
    endpoint: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=200)


class TestConnectionResponse(BaseModel):
    ok: bool
    status: str  # connected | auth_failed | unreachable | invalid_response
    message: str
    models: list[str] = []
    model_count: int = 0
    selected_model: str | None = None
    selected_model_found: bool | None = None
    # Non-fatal advisory, e.g. the endpoint uses plain http:// so the key travels unencrypted.
    warning: str | None = None
