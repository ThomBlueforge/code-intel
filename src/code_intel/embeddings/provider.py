"""Embedding providers.

Two implementations behind one ``EmbeddingProvider`` protocol:

- ``HashingEmbeddingProvider`` — deterministic, dependency-free, offline. Hashes
  tokens into a fixed-dimension bag-of-words vector. Good enough for tests and
  fully local operation with no model server.
- ``OpenAICompatibleEmbeddingProvider`` — calls a configured ``/embeddings``
  endpoint. Chosen when a real embedding model is available.

Both are swappable; callers depend only on the protocol.
"""

from __future__ import annotations

import math
import re
from typing import Protocol

import httpx

from code_intel.config import LLMSettings

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_DEFAULT_HASH_DIM = 256


class EmbeddingProvider(Protocol):
    """Turns texts into fixed-length vectors."""

    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbeddingProvider:
    """Deterministic, offline hashing embedder (feature hashing + L2 norm)."""

    def __init__(self, dimension: int = _DEFAULT_HASH_DIM) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        for token in _tokenize(text):
            bucket = hash(token) % self._dimension
            sign = 1.0 if (hash(token + "#sign") & 1) else -1.0
            vec[bucket] += sign
        return _l2_normalize(vec)


class OpenAICompatibleEmbeddingProvider:
    """Embeds via an OpenAI-compatible ``/embeddings`` endpoint."""

    def __init__(
        self, settings: LLMSettings, model: str, client: httpx.Client | None = None
    ) -> None:
        self._settings = settings
        self._model = model
        self._client = client or httpx.Client(timeout=settings.request_timeout_s)
        self._dimension = 0  # discovered on first response

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._settings.batch_size):
            batch = texts[start : start + self._settings.batch_size]
            vectors.extend(self._embed_batch(batch))
        return vectors

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        url = f"{self._settings.base_url.rstrip('/')}/embeddings"
        headers = {"Authorization": f"Bearer {self._settings.api_key}"}
        response = self._client.post(
            url, json={"model": self._model, "input": batch}, headers=headers
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        vectors = [item["embedding"] for item in data]
        if vectors and self._dimension == 0:
            self._dimension = len(vectors[0])
        return vectors

    def close(self) -> None:
        self._client.close()


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]
