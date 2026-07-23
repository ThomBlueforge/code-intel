# Phase 17 — Local LLM Client

## What was built

A single OpenAI-compatible client (`llm/client.py`) behind the `ChatClient`
protocol, and an embedding client (`embeddings/provider.py`). **No vendor
lock-in, nothing hardcoded** — every parameter is configuration.

## Fully configurable (via `LLMSettings`)

| Setting | Env var | Default |
|---------|---------|---------|
| base_url | `CODE_INTEL_LLM_BASE_URL` | `http://localhost:5000/v1` |
| api_key | `CODE_INTEL_LLM_API_KEY` | `not-needed-for-local` |
| model | `CODE_INTEL_LLM_MODEL` | `local-model` |
| temperature | `CODE_INTEL_LLM_TEMPERATURE` | `0.0` |
| max_tokens | `CODE_INTEL_LLM_MAX_TOKENS` | `1024` |
| request_timeout_s | `CODE_INTEL_LLM_TIMEOUT` | `120` |
| max_retries | `CODE_INTEL_LLM_MAX_RETRIES` | `3` |
| batch_size | `CODE_INTEL_LLM_BATCH_SIZE` | `8` |
| max_concurrency | `CODE_INTEL_LLM_CONCURRENCY` | `4` |

`LLMSettings.from_env()` reads all of them; `code-intel config` prints the
effective values. CLI flags (`--base-url`, `--model`) override per command.

## Design

- Callers depend on the `ChatClient` protocol, so a fake is injected in tests
  and no network is needed for deterministic layers.
- Works with Text Generation Web UI, llama.cpp server, vLLM, Ollama's OpenAI
  mode, or any OpenAI-compatible endpoint.
- Retries with capped exponential backoff; raises `LLMError` after exhaustion so
  callers can degrade.

## Definition of Done

- [x] Fully configurable OpenAI-compatible client — base_url, key, model,
      temperature, tokens, timeout, retries, batch size, concurrency.
- [x] No vendor lock-in; nothing hardcoded (verified by `test_config.py`).
