"""AIProviderAdapter protocol — BYOK, mirrors the existing BrokerAdapter
protocol (app/integrations/brokers/base.py) deliberately: same shape of
problem (user brings their own third-party credential; QFinance/Qfinera
never stores or provides one of its own), same solution (a narrow protocol,
lazy SDK import in the concrete adapter, a *_NotConfigured/*_Error exception
split).

WRITTEN, NOT EXECUTED.
"""
from typing import Protocol


class AIProviderError(Exception):
    """A genuine call failure: invalid/expired key, provider API error,
    network failure, rate limit. Never raised merely because no key is
    connected — see AIProviderNotConfiguredError for that case."""


class AIProviderNotConfiguredError(Exception):
    """Raised when the caller has no connected key for this provider. The
    service layer converts this into the AI_NOT_CONNECTED error the API
    contract documents ('Connect your AI provider')."""


class AIProviderAdapter(Protocol):
    def ask(self, *, api_key: str, question: str, context: str) -> str:
        """Returns the answer text. `api_key` is the caller's own BYOK key,
        passed per-call — never cached on the adapter instance, never logged,
        never included in any exception message raised from here.
        `context` is prior accumulated research context (already-saved
        research_notes answers plus already-filled Q-RESEARCH fields),
        concatenated by the caller (ai/service.py), not by this adapter."""
        ...
