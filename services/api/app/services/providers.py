from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class ModelCapability:
    provider: str
    model: str
    supports_chat: bool
    supports_streaming: bool
    supports_embeddings: bool
    supports_structured_output: bool
    maximum_context_window: int
    maximum_output_tokens: int
    status: str = "configurable"


DEFAULT_CAPABILITIES = [
    ModelCapability("OpenAI", "gpt-4.1", True, True, False, True, 1_000_000, 16_384),
    ModelCapability("OpenAI", "text-embedding-3-large", False, False, True, False, 8_191, 0),
    ModelCapability("Anthropic", "claude-sonnet-4", True, True, False, True, 200_000, 64_000),
    ModelCapability("Google Gemini", "gemini-2.5-pro", True, True, False, True, 1_000_000, 65_536),
    ModelCapability("xAI Grok", "grok-3", True, True, False, True, 131_072, 16_384),
    ModelCapability("Local", "deterministic-local-384", False, False, True, False, 8_191, 0),
]


class ChatProvider:
    async def stream_chat(self, messages: list[dict[str, str]], model_config: dict[str, Any], context: str):
        raise NotImplementedError


async def test_provider_connection(provider: str, api_key: str, base_url: str | None = None) -> dict[str, Any]:
    if provider == "Local":
        return {"status": "ok", "message": "Local deterministic provider is available."}
    url = base_url or _default_url(provider)
    headers = _headers(provider, api_key)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, headers=headers)
        return {"status": "ok" if response.status_code < 500 else "error", "status_code": response.status_code}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _default_url(provider: str) -> str:
    return {
        "OpenAI": "https://api.openai.com/v1/models",
        "Anthropic": "https://api.anthropic.com/v1/models",
        "Google Gemini": "https://generativelanguage.googleapis.com/v1beta/models",
        "xAI Grok": "https://api.x.ai/v1/models",
    }[provider]


def _headers(provider: str, api_key: str) -> dict[str, str]:
    if provider == "Anthropic":
        return {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    if provider == "Google Gemini":
        return {"x-goog-api-key": api_key}
    return {"Authorization": f"Bearer {api_key}"}
