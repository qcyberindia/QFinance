"""AI provider abstraction — mirrors the existing BrokerAdapter (portfolio)
and PaymentService (billing) pattern: calling code (research_ai/service.py)
depends only on this Protocol, never on a specific provider's SDK/HTTP shape
directly, so a second provider can be added as a new adapter file without
touching any calling code.
WRITTEN, NOT EXECUTED — no real network call has been made in this session.
"""
from typing import Protocol


class AiProviderError(Exception):
    """Raised for any provider-call failure (bad key, network error, rate
    limit, malformed response) — callers show a clean error, never a stack
    trace, and never log the API key that was used."""


class AiProvider(Protocol):
    async def ask(self, *, api_key: str, system_prompt: str, question: str) -> str:
        """Returns the model's answer as plain text. Implementations must
        never log `api_key` under any circumstance, including on error."""
        ...
