from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.core.config import settings


class EmbeddingProvider(ABC):
    dimension: int
    model_name: str

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class DeterministicEmbeddingProvider(EmbeddingProvider):
    dimension = 384
    model_name = "deterministic-local-384"

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [deterministic_embedding(text, self.dimension) for text in texts]


def deterministic_embedding(text: str, dimension: int = 384) -> list[float]:
    vector = [0.0] * dimension
    tokens = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
    for token in tokens:
        digest = hashlib.blake2b(token.encode(), digest_size=16).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * (1.0 + min(len(token), 16) / 16)
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / norm, 6) for value in vector]


def get_embedding_provider(provider: str = "Local") -> EmbeddingProvider:
    if provider == "Local" and settings.enable_dev_embedding_provider:
        return DeterministicEmbeddingProvider()
    raise ValueError(f"Embedding provider {provider} is not configured.")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)
