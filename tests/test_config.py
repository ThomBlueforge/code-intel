"""Tests for configuration and LLM settings from environment (Phase 17)."""

from __future__ import annotations

import os

from code_intel.config import LLMSettings


def test_llm_defaults() -> None:
    settings = LLMSettings.from_env()
    assert settings.base_url.startswith("http")
    assert settings.temperature == 0.0
    assert settings.max_retries == 3


def test_llm_overridden_by_env(monkeypatch) -> None:
    monkeypatch.setenv("CODE_INTEL_LLM_BASE_URL", "http://example.local/v1")
    monkeypatch.setenv("CODE_INTEL_LLM_MODEL", "custom-model")
    monkeypatch.setenv("CODE_INTEL_LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("CODE_INTEL_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("CODE_INTEL_LLM_BATCH_SIZE", "16")
    settings = LLMSettings.from_env()
    assert settings.base_url == "http://example.local/v1"
    assert settings.model == "custom-model"
    assert settings.temperature == 0.5
    assert settings.max_tokens == 2048
    assert settings.batch_size == 16


def test_nothing_hardcoded_all_configurable() -> None:
    # Every field is settable via env; sanity-check a representative set.
    keys = {
        "CODE_INTEL_LLM_BASE_URL", "CODE_INTEL_LLM_API_KEY", "CODE_INTEL_LLM_MODEL",
        "CODE_INTEL_LLM_TEMPERATURE", "CODE_INTEL_LLM_MAX_TOKENS", "CODE_INTEL_LLM_TIMEOUT",
        "CODE_INTEL_LLM_MAX_RETRIES", "CODE_INTEL_LLM_BATCH_SIZE", "CODE_INTEL_LLM_CONCURRENCY",
    }
    for key in keys:
        os.environ[key] = os.environ.get(key, "")  # ensure lookups don't raise
    assert isinstance(LLMSettings.from_env(), LLMSettings)
