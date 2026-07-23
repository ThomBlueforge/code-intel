"""Embedding pipeline.

For each enriched symbol, builds one embedding input from the whole logical unit
plus its enrichment, embeds it, writes a traceability record to SQLite, and
pushes the vector + rich payload to a ``VectorSink``. Incremental: a symbol whose
embedding input hash is unchanged is skipped unless ``force``.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass

from code_intel.embeddings.provider import EmbeddingProvider
from code_intel.embeddings.sink import EmbeddedUnit, VectorSink
from code_intel.models import EmbeddingRecord, EnrichedSymbol, Symbol, utc_now_iso
from code_intel.storage.repositories import (
    EmbeddingStore,
    EnrichedSymbolStore,
    SymbolStore,
)

_MAX_PAYLOAD_CODE_CHARS = 2000
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@dataclass(frozen=True)
class EmbeddingReport:
    embedded: int
    skipped: int
    total_embedded_in_repo: int
    dimension: int


class EmbeddingPipeline:
    """Embeds enriched symbols and writes them to a vector sink."""

    def __init__(self, conn: sqlite3.Connection, provider: EmbeddingProvider, model: str) -> None:
        self._conn = conn
        self._provider = provider
        self._model = model

    def run(
        self,
        repository_id: str,
        sink: VectorSink,
        *,
        limit: int | None = None,
        force: bool = False,
    ) -> EmbeddingReport:
        symbols = SymbolStore(self._conn).list_for_repository(repository_id)
        enriched_store = EnrichedSymbolStore(self._conn)
        emb_store = EmbeddingStore(self._conn)
        existing = emb_store.embedded_hashes()

        pending: list[tuple[Symbol, EnrichedSymbol, str, str]] = []
        skipped = 0
        for symbol in symbols:
            enriched = enriched_store.get(symbol.id)
            if enriched is None:  # only embed enriched units (runs after Phase 6)
                skipped += 1
                continue
            text = _embedding_text(symbol, enriched)
            content_hash = _hash_text(text)
            if not force and existing.get(symbol.id) == content_hash:
                skipped += 1
                continue
            pending.append((symbol, enriched, text, content_hash))
            if limit is not None and len(pending) >= limit:
                break

        vectors = self._provider.embed([text for _, _, text, _ in pending]) if pending else []
        now = utc_now_iso()
        units: list[EmbeddedUnit] = []
        for (symbol, enriched, _text, content_hash), vector in zip(pending, vectors, strict=True):
            units.append(
                EmbeddedUnit(
                    symbol_id=symbol.id,
                    vector=vector,
                    content_hash=content_hash,
                    model=self._model,
                    dimension=self._provider.dimension,
                    payload=_payload(symbol, enriched),
                )
            )
            emb_store.upsert(
                EmbeddingRecord(
                    symbol_id=symbol.id,
                    model=self._model,
                    dimension=self._provider.dimension,
                    content_hash=content_hash,
                    created_at=now,
                )
            )

        if units:
            sink.upsert(units)
        self._conn.commit()
        return EmbeddingReport(
            embedded=len(units),
            skipped=skipped,
            total_embedded_in_repo=emb_store.count(),
            dimension=self._provider.dimension,
        )


def _embedding_text(symbol: Symbol, enriched: EnrichedSymbol) -> str:
    domains = ", ".join(enriched.business_domain)
    return (
        f"{symbol.type} {symbol.name} [{symbol.language}]\n"
        f"summary: {enriched.summary}\n"
        f"domain: {domains}\n"
        f"layer: {enriched.architecture_layer}\n"
        f"code:\n{symbol.code}"
    )


def _payload(symbol: Symbol, enriched: EnrichedSymbol) -> dict[str, object]:
    return {
        "symbol_id": symbol.id,
        "repository_id": symbol.repository_id,
        "path": symbol.path,
        "name": symbol.name,
        "kind": symbol.type,
        "language": symbol.language,
        "parent_symbol_id": symbol.parent_id or "",
        "summary": enriched.summary,
        "business_domain": enriched.business_domain,
        "architecture_layer": enriched.architecture_layer,
        "keywords": _keywords(symbol.name),
        "complexity": enriched.quality_metrics.complexity,
        "hash": symbol.hash,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "code": symbol.code[:_MAX_PAYLOAD_CODE_CHARS],
    }


def _keywords(name: str) -> list[str]:
    parts = _CAMEL_RE.sub(" ", name).replace("_", " ").split()
    return sorted({p.lower() for p in parts if p})


def _hash_text(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()
