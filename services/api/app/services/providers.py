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
    embedding_dimension: int | None = None
    status: str = "configurable"


DEFAULT_CAPABILITIES = [
    ModelCapability("OpenAI", "gpt-4.1", True, True, False, True, 1_000_000, 16_384),
    ModelCapability("OpenAI", "gpt-4.1-mini", True, True, False, True, 1_000_000, 16_384),
    ModelCapability("OpenAI", "gpt-4o", True, True, False, True, 128_000, 16_384),
    ModelCapability("OpenAI", "gpt-4o-mini", True, True, False, True, 128_000, 16_384),
    ModelCapability(
        "OpenAI", "text-embedding-3-small", False, False, True, False, 8_191, 0, 1_536
    ),
    ModelCapability(
        "OpenAI", "text-embedding-3-large", False, False, True, False, 8_191, 0, 3_072
    ),
    ModelCapability(
        "OpenAI", "text-embedding-ada-002", False, False, True, False, 8_191, 0, 1_536
    ),
    ModelCapability("Anthropic", "claude-opus-4", True, True, False, True, 200_000, 32_000),
    ModelCapability("Anthropic", "claude-sonnet-4", True, True, False, True, 200_000, 64_000),
    ModelCapability("Anthropic", "claude-3-5-haiku-latest", True, True, False, True, 200_000, 8_192),
    ModelCapability("Google Gemini", "gemini-2.5-pro", True, True, False, True, 1_000_000, 65_536),
    ModelCapability("Google Gemini", "gemini-2.5-flash", True, True, False, True, 1_000_000, 65_536),
    ModelCapability(
        "Google Gemini", "text-embedding-004", False, False, True, False, 2_048, 0, 768
    ),
    ModelCapability("xAI Grok", "grok-3", True, True, False, True, 131_072, 16_384),
    ModelCapability("xAI Grok", "grok-3-mini", True, True, False, True, 131_072, 16_384),
    ModelCapability("Local", "deterministic-local-384", True, False, True, False, 8_191, 0, 384),
]


class ChatProvider:
    async def stream_chat(self, messages: list[dict[str, str]], model_config: dict[str, Any], context: str):
        raise NotImplementedError


async def test_provider_connection(provider: str, api_key: str, base_url: str | None = None) -> dict[str, Any]:
    if provider == "Local":
        models = [capability.model for capability in DEFAULT_CAPABILITIES if capability.provider == "Local"]
        return {
            "status": "ok",
            "message": "Local deterministic provider is available.",
            "models": models,
        }
    url = _models_url(provider, base_url)
    headers = _headers(provider, api_key)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(url, headers=headers)
        models = _parse_model_ids(provider, response.json()) if response.status_code < 500 else []
        return {
            "status": "ok" if response.status_code < 500 else "error",
            "status_code": response.status_code,
            "models": models[:200],
            "model_count": len(models),
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


async def discover_provider_models(
    provider: str,
    api_key: str,
    base_url: str | None = None,
) -> list[ModelCapability]:
    if provider == "Local":
        return default_capabilities_for_provider(provider)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.get(_models_url(provider, base_url), headers=_headers(provider, api_key))
        response.raise_for_status()
        model_ids = _parse_model_ids(provider, response.json())
    except Exception:
        return default_capabilities_for_provider(provider)
    capabilities = [infer_capability(provider, model_id) for model_id in model_ids]
    filtered = [
        capability
        for capability in capabilities
        if capability.supports_chat or capability.supports_embeddings
    ]
    return filtered or default_capabilities_for_provider(provider)


def default_capabilities_for_provider(provider: str) -> list[ModelCapability]:
    return [capability for capability in DEFAULT_CAPABILITIES if capability.provider == provider]


def infer_capability(provider: str, model: str) -> ModelCapability:
    embedding_dimension = embedding_dimension_for_model(provider, model)
    supports_embeddings = embedding_dimension is not None
    supports_chat = not supports_embeddings and _looks_like_chat_model(provider, model)
    defaults = next(
        (
            capability
            for capability in DEFAULT_CAPABILITIES
            if capability.provider == provider and capability.model == model
        ),
        None,
    )
    if defaults:
        return defaults
    return ModelCapability(
        provider=provider,
        model=model,
        supports_chat=supports_chat,
        supports_streaming=supports_chat,
        supports_embeddings=supports_embeddings,
        supports_structured_output=supports_chat and provider in {"OpenAI", "Anthropic", "Google Gemini"},
        maximum_context_window=0,
        maximum_output_tokens=0,
        embedding_dimension=embedding_dimension,
        status="discovered",
    )


def embedding_dimension_for_model(provider: str, model: str) -> int | None:
    normalized = model.lower()
    known_dimensions = {
        ("Local", "deterministic-local-384"): 384,
        ("OpenAI", "text-embedding-3-small"): 1_536,
        ("OpenAI", "text-embedding-3-large"): 3_072,
        ("OpenAI", "text-embedding-ada-002"): 1_536,
        ("Google Gemini", "text-embedding-004"): 768,
        ("Google Gemini", "embedding-001"): 768,
    }
    if (provider, model) in known_dimensions:
        return known_dimensions[(provider, model)]
    if provider == "OpenAI" and "embedding" in normalized:
        return 3_072 if "large" in normalized else 1_536
    if provider == "Google Gemini" and "embedding" in normalized:
        return 768
    return None


def _default_models_url(provider: str) -> str:
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


def _models_url(provider: str, base_url: str | None = None) -> str:
    if not base_url:
        return _default_models_url(provider)
    base = base_url.rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def _parse_model_ids(provider: str, payload: dict[str, Any]) -> list[str]:
    if provider == "Google Gemini":
        models = payload.get("models", [])
        return [
            str(item.get("name", "")).removeprefix("models/")
            for item in models
            if item.get("name")
        ]
    data = payload.get("data", [])
    return [str(item.get("id")) for item in data if item.get("id")]


def _looks_like_chat_model(provider: str, model: str) -> bool:
    normalized = model.lower()
    excluded_terms = (
        "embedding",
        "tts",
        "whisper",
        "dall-e",
        "moderation",
        "rerank",
        "image",
        "vision-preview",
    )
    if any(term in normalized for term in excluded_terms):
        return False
    if provider == "Google Gemini":
        return normalized.startswith("gemini")
    return True
