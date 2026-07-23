"""LLM access layer (Phase 17, used from Phase 6 onward).

A single, fully-configurable OpenAI-compatible client behind a narrow
``ChatClient`` protocol. No vendor lock-in: base URL, key, model, temperature,
token limits, timeouts, and retries all come from configuration. Nothing else
in the platform constructs its own LLM connection.
"""
