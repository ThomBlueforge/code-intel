"""Symbol enrichment orchestration.

Calls the injected ``ChatClient`` per symbol, parses the JSON response
defensively, coerces classifications to the controlled ontology, and persists
the result via ``EnrichedSymbolStore``. Any parse/validation failure degrades to
an explicit low-confidence "Unknown" record — the platform never fabricates
understanding.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from code_intel.enrichment.prompts import (
    ARCHITECTURE_LAYERS,
    BUSINESS_DOMAINS,
    RESPONSIBILITIES,
    build_messages,
)
from code_intel.llm.client import ChatClient, LLMError
from code_intel.models import EnrichedSymbol, QualityMetrics, Symbol, utc_now_iso
from code_intel.storage.repositories import EnrichedSymbolStore, SymbolStore

# Symbol kinds worth enriching (logical units, not bare constants/globals).
ENRICHABLE_TYPES: frozenset[str] = frozenset(
    {"function", "method", "class", "interface", "struct", "trait", "enum"}
)
_METRIC_KEYS = (
    "complexity", "maintainability", "readability", "coupling", "cohesion",
    "testability", "risk", "stability", "reusability", "technical_debt",
)


@dataclass(frozen=True)
class EnrichmentReport:
    enriched: int
    skipped: int
    failed: int
    total_enriched_in_repo: int


class Enricher:
    """Enriches symbols using a configurable chat model."""

    def __init__(self, conn: sqlite3.Connection, client: ChatClient, model: str) -> None:
        self._conn = conn
        self._client = client
        self._model = model

    def enrich_symbol(self, symbol: Symbol) -> EnrichedSymbol:
        """Enrich one symbol. Never raises for bad model output — degrades."""
        try:
            raw = self._client.complete(build_messages(symbol))
            data = _parse_json(raw)
        except (LLMError, ValueError):
            data = None
        return self._to_enriched(symbol, data)

    def enrich_repository(
        self,
        repository_id: str,
        *,
        limit: int | None = None,
        force: bool = False,
    ) -> EnrichmentReport:
        symbols = SymbolStore(self._conn).list_for_repository(repository_id)
        store = EnrichedSymbolStore(self._conn)
        already = set() if force else store.enriched_ids()

        enriched = skipped = failed = 0
        for symbol in symbols:
            if symbol.type not in ENRICHABLE_TYPES:
                skipped += 1
                continue
            if symbol.id in already:
                skipped += 1
                continue
            if limit is not None and enriched >= limit:
                break
            result = self.enrich_symbol(symbol)
            store.upsert(result)
            if result.confidence <= 0.0 and result.summary == "Unknown":
                failed += 1
            else:
                enriched += 1
        self._conn.commit()
        return EnrichmentReport(
            enriched=enriched,
            skipped=skipped,
            failed=failed,
            total_enriched_in_repo=store.count(),
        )

    def _to_enriched(self, symbol: Symbol, data: dict[str, object] | None) -> EnrichedSymbol:
        now = utc_now_iso()
        if data is None:
            return _unknown(symbol, self._model, now)
        return EnrichedSymbol(
            symbol_id=symbol.id,
            summary=_as_str(data.get("summary"), "Unknown"),
            business_domain=_filter_vocab(data.get("business_domain"), BUSINESS_DOMAINS, "Unknown"),
            architecture_layer=_one_of(
                data.get("architecture_layer"), ARCHITECTURE_LAYERS, "Unknown"
            ),
            responsibilities=_filter_vocab(data.get("responsibilities"), RESPONSIBILITIES, None),
            quality_metrics=_parse_metrics(data.get("quality_metrics")),
            risks=_as_str_list(data.get("risks")),
            technical_debt=_as_str_list(data.get("technical_debt")),
            confidence=_clamp(_as_float(data.get("confidence"), 0.0)),
            model=self._model,
            created_at=now,
            updated_at=now,
        )


def _unknown(symbol: Symbol, model: str, now: str) -> EnrichedSymbol:
    return EnrichedSymbol(
        symbol_id=symbol.id,
        summary="Unknown",
        business_domain=["Unknown"],
        architecture_layer="Unknown",
        responsibilities=[],
        quality_metrics=QualityMetrics(),
        risks=[],
        technical_debt=[],
        confidence=0.0,
        model=model,
        created_at=now,
        updated_at=now,
    )


def _parse_json(raw: str) -> dict[str, object]:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in response")
    parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("JSON root is not an object")
    return parsed


def _as_str(value: object, default: str) -> str:
    return value if isinstance(value, str) and value.strip() else default


def _as_float(value: object, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _filter_vocab(
    value: object, vocab: frozenset[str], empty_fallback: str | None
) -> list[str]:
    items = [item for item in _as_str_list(value) if item in vocab]
    if not items and empty_fallback is not None:
        return [empty_fallback]
    return items


def _one_of(value: object, vocab: frozenset[str], default: str) -> str:
    return value if isinstance(value, str) and value in vocab else default


def _parse_metrics(value: object) -> QualityMetrics:
    if not isinstance(value, dict):
        return QualityMetrics()
    scores = {key: _clamp(_as_float(value.get(key), 0.0)) for key in _METRIC_KEYS}
    return QualityMetrics(**scores)
