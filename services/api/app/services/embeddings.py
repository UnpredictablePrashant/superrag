from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings


class EmbeddingProvider(ABC):
    dimension: int
    model_name: str

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class DeterministicEmbeddingProvider(EmbeddingProvider):
    model_name = "deterministic-local-384"

    def __init__(self, dimension: int | None = None) -> None:
        self.dimension = dimension or settings.deterministic_embedding_dimension

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [deterministic_embedding(text, self.dimension) for text in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model_name: str = "text-embedding-3-small",
        base_url: str | None = None,
        dimension: int | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI embedding provider requires an API key.")
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.dimension = dimension or 1536

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, object] = {"model": self.model_name, "input": texts}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        response.raise_for_status()
        data = response.json().get("data", [])
        ordered = sorted(data, key=lambda item: item.get("index", 0))
        return [list(item["embedding"]) for item in ordered]


def deterministic_embedding(text: str, dimension: int = 384) -> list[float]:
    vector = [0.0] * dimension
    tokens = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode(), digest_size=16).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + min(len(token), 16) / 16)
    return normalize_vector(vector)


def get_embedding_provider(
    provider: str = "Local",
    *,
    model_name: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    dimension: int | None = None,
) -> EmbeddingProvider:
    if provider == "Local":
        return DeterministicEmbeddingProvider(dimension=dimension)
    if provider == "OpenAI":
        return OpenAIEmbeddingProvider(
            api_key=api_key or "",
            model_name=model_name or "text-embedding-3-small",
            base_url=base_url,
            dimension=dimension,
        )
    raise ValueError(f"Embedding provider {provider} is not configured.")


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)
