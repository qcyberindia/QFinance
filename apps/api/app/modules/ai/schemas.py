"""Pydantic schemas — ai module. No field named api_key/key/token appears in
ANY response schema below, on purpose — structurally, not just by
discipline, matching portfolio/schemas.py's precedent."""
from datetime import datetime

from pydantic import BaseModel


class ConnectRequest(BaseModel):
    provider: str = "anthropic"
    api_key: str


class StatusResponse(BaseModel):
    connected: bool
    provider: str | None
    connected_at: datetime | None
