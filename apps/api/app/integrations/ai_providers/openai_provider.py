"""OpenAI-compatible chat-completions provider — the one AI provider actually
implemented for MVP (SUPPORTED_PROVIDERS = ("openai",) in research_ai/models.py).
Uses the member's OWN API key (BYOK) — Qfinera never supplies or hardcodes a
key here. The key is received as a parameter at call time only; it is never
stored, cached, or logged by this module.
WRITTEN, NOT EXECUTED — no real network call to api.openai.com has been made
in this session (this project's network sandbox does not allow that host;
this code has not been exercised against the real OpenAI API by me).
"""
import httpx

from app.integrations.ai_providers.base import AiProviderError

CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-4o-mini"  # a reasonably-priced default; not user-configurable in MVP
REQUEST_TIMEOUT_SECONDS = 30.0


class OpenAiProvider:
    async def ask(self, *, api_key: str, system_prompt: str, question: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    CHAT_COMPLETIONS_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": MODEL,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": question},
                        ],
                        "temperature": 0.3,
                    },
                )
        except httpx.HTTPError as e:
            # Deliberately does not include `e`'s full detail in a way that
            # could echo request headers/body (which would contain the key) —
            # httpx's own HTTPError.__str__ is URL/status based, not body-based
            # (same reasoning already documented for email_service.py).
            raise AiProviderError("Could not reach the AI provider. Please try again.") from e

        if response.status_code == 401:
            raise AiProviderError("Your AI provider rejected this API key. Please reconnect it.")
        if response.status_code == 429:
            raise AiProviderError("Your AI provider is rate-limiting this key. Please try again shortly.")
        if response.status_code >= 400:
            raise AiProviderError(f"The AI provider returned an error (status {response.status_code}).")

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise AiProviderError("The AI provider returned an unexpected response.") from e
