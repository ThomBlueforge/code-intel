"""OpenAI-compatible chat client.

Talks to any endpoint implementing the OpenAI ``/chat/completions`` shape
(Text Generation Web UI, llama.cpp server, vLLM, Ollama's OpenAI mode, etc.).
Every parameter is injected via ``LLMSettings`` — none are hardcoded. Callers
depend on the ``ChatClient`` protocol so tests can substitute a fake and no
network is required for the deterministic layers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from code_intel.config import LLMSettings


@dataclass(frozen=True)
class ChatMessage:
    """A single chat message."""

    role: str  # "system" | "user" | "assistant"
    content: str


class LLMError(RuntimeError):
    """Raised when the LLM endpoint cannot produce a completion."""


class ChatClient(Protocol):
    """Minimal chat interface the enrichment layer depends on."""

    def complete(self, messages: list[ChatMessage]) -> str: ...


class OpenAICompatibleClient:
    """Concrete ``ChatClient`` over an OpenAI-compatible HTTP endpoint."""

    def __init__(self, settings: LLMSettings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.request_timeout_s)

    def complete(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self._settings.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }
        headers = {"Authorization": f"Bearer {self._settings.api_key}"}
        url = f"{self._settings.base_url.rstrip('/')}/chat/completions"

        last_error: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                return _extract_content(response.json())
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                last_error = exc
                if attempt < self._settings.max_retries:
                    time.sleep(_backoff_seconds(attempt))
        raise LLMError(f"LLM request failed after retries: {last_error}") from last_error

    def close(self) -> None:
        self._client.close()


def _extract_content(body: dict[str, object]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM response contained no choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ValueError("LLM response missing message content")
    return content


def _backoff_seconds(attempt: int) -> float:
    return min(2.0**attempt, 8.0)
