"""AnthropicAdapter — the only BYOK provider in this MVP. Wraps the
`anthropic` SDK, mirroring `integrations/brokers/zerodha.py`'s lazy-import
pattern exactly (this module must remain importable with no `anthropic`
package installed, so the application still starts).

SECURITY BOUNDARY, restated: `api_key` is a per-call parameter, never stored
as an instance/module attribute, never included in any log line or
exception message anywhere in this file.

WRITTEN, NOT EXECUTED — no real Anthropic API call has been made in this
session; no real user-supplied key exists in this environment.
"""
import logging

from app.integrations.ai.base import AIProviderError

logger = logging.getLogger("qfinera.ai.anthropic")

_SYSTEM_PROMPT = (
    "You are a research assistant helping a retail investor think through a company, "
    "industry, or macro topic for their own personal investment research notes. "
    "Answer the user's specific question directly, using the research context they provide. "
    "Do not give personalized buy, sell, or hold recommendations, price targets, or trading "
    "signals — explain reasoning, trade-offs, and what evidence would support or weaken a view. "
    "If you are not confident about a specific fact (e.g. an exact recent number), say so rather "
    "than inventing a figure."
)


class AnthropicAdapter:
    """Implements the AIProviderAdapter protocol (see base.py)."""

    def ask(self, *, api_key: str, question: str, context: str) -> str:
        try:
            import anthropic
        except ImportError as e:
            raise AIProviderError("The 'anthropic' package is not installed.") from e

        client = anthropic.Anthropic(api_key=api_key)
        user_content = (
            f"Accumulated research context so far:\n{context}\n\n---\n\nQuestion: {question}"
            if context.strip() else f"Question: {question}"
        )
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception as e:  # noqa: BLE001 — the SDK's exception hierarchy isn't
            # guaranteed importable if the package itself is absent; converting any
            # failure here uniformly to AIProviderError keeps this adapter's public
            # contract stable, same reasoning as ZerodhaAdapter's equivalent catches.
            logger.warning("Anthropic request failed: %s", type(e).__name__)
            raise AIProviderError("The AI provider request failed.") from e

        text_blocks = [block.text for block in response.content if getattr(block, "type", None) == "text"]
        return "\n".join(text_blocks).strip()
