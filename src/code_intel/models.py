"""Canonical data models.

These are the authoritative in-memory representations. Downstream layers must
not redefine equivalent structures. Phase 1 uses ``Repository`` and
``FileRecord``; the symbol/enrichment/relationship models arrive in later
phases and will be added here rather than elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string (timezone-aware)."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Repository:
    """A single indexed repository root."""

    id: str
    path: str
    name: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class FileRecord:
    """A text/code file recorded in the manifest.

    ``path`` is repository-relative and POSIX-normalised so the manifest is
    stable across platforms. ``hash`` is the content hash used for incremental
    change detection.
    """

    id: str
    repository_id: str
    path: str
    language: str
    hash: str
    size_bytes: int
    mtime: float
    created_at: str
    updated_at: str


# Canonical symbol kinds. Anything the parser cannot place here is not emitted.
SYMBOL_TYPES: frozenset[str] = frozenset(
    {
        "function",
        "method",
        "class",
        "interface",
        "struct",
        "trait",
        "enum",
        "const",
        "global",
        "module",
        "namespace",
    }
)

VISIBILITY_VALUES: frozenset[str] = frozenset(
    {"public", "private", "protected", "internal", "unknown"}
)


@dataclass(frozen=True)
class Symbol:
    """A deterministic code symbol extracted by Tree-sitter (Phase 2).

    Matches the canonical Symbol schema. This is a *fact*: no LLM is involved
    in producing it. ``code`` holds the full source of the logical unit;
    ``signature`` is its declaration line. ``parent_id`` links a nested symbol
    (e.g. a method) to its enclosing symbol (e.g. a class).
    """

    id: str
    repository_id: str
    file_id: str
    name: str
    type: str
    language: str
    path: str
    start_line: int
    end_line: int
    signature: str
    visibility: str
    parent_id: str | None
    code: str
    hash: str
    created_at: str
    updated_at: str
    # Normalised decorator/annotation names (e.g. "property", "router.get").
    # Empty for undecorated symbols. Persisted comma-joined; see SymbolStore.
    decorators: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualityMetrics:
    """AI-estimated quality scores, each in [0.0, 1.0]."""

    complexity: float = 0.0
    maintainability: float = 0.0
    readability: float = 0.0
    coupling: float = 0.0
    cohesion: float = 0.0
    testability: float = 0.0
    risk: float = 0.0
    stability: float = 0.0
    reusability: float = 0.0
    technical_debt: float = 0.0


@dataclass(frozen=True)
class EnrichedSymbol:
    """AI understanding of a symbol (Phase 6).

    This is the *enrichment* layer: it always references a deterministic
    ``Symbol`` by ``symbol_id`` and never replaces or overrides structural
    facts. ``confidence`` is mandatory; the enricher emits low confidence and
    "Unknown" rather than guessing.
    """

    symbol_id: str
    summary: str
    business_domain: list[str]
    architecture_layer: str
    responsibilities: list[str]
    quality_metrics: QualityMetrics
    risks: list[str]
    technical_debt: list[str]
    confidence: float
    model: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EmbeddingRecord:
    """Traceability record that a symbol has been embedded (Phase 7).

    The embedding *vector itself* is never stored in SQLite — it lives in the
    vector store (Qdrant). This row only proves an embedding exists and lets us
    detect staleness via ``content_hash``.
    """

    symbol_id: str
    model: str
    dimension: int
    content_hash: str
    created_at: str


@dataclass(frozen=True)
class Summary:
    """A hierarchical summary (Phase 11 — repository memory).

    ``scope`` is one of function/method/class/module/package/repository.
    ``target_key`` is a symbol id (for symbol scopes), a path (module/package),
    or a repository id. ``source`` records how it was produced.
    """

    scope: str
    target_key: str
    path: str
    summary: str
    source: str  # "aggregate" (deterministic rollup) | "llm"
    confidence: float
    created_at: str


@dataclass(frozen=True)
class Finding:
    """An intelligence finding (Phases 13 & 21).

    Carries provenance and confidence so deterministic and inferred findings
    stay separable, never silently merged.
    """

    id: str
    repository_id: str
    category: str  # e.g. "god_object", "circular_dependency", "design_pattern"
    title: str
    detail: str
    origin: str  # STATIC_ANALYSIS | LLM_INFERENCE | USER_DEFINED
    confidence: float
    target: str  # path / symbol name / concept
    created_at: str


@dataclass(frozen=True)
class FileUnderstanding:
    """Holistic understanding of one file (Phase 23 — codebase comprehension).

    Built bottom-up from the file's symbol understandings, so it describes what
    the file *does* and its enumerated ``responsibilities`` rather than merely
    counting symbols. ``source`` is "llm" or "aggregate" (deterministic
    fallback); ``content_hash`` fingerprints the file's symbol set for
    incremental rebuilds. Kept separate from deterministic facts and rebuildable.
    """

    repository_id: str
    path: str
    summary: str
    responsibilities: list[str]  # enumerated: what the file does, item by item
    key_exports: list[str]
    collaborators: list[str]  # modules it imports / is imported by
    role: str  # short architectural role, e.g. "storage", "http api"
    source: str  # "aggregate" | "llm"
    confidence: float
    content_hash: str
    model: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RepoUnderstanding:
    """Top-level architectural overview of a repository (Phase 23).

    Synthesised from the file understandings — the orientation an agent would
    build first: what the project is, how its modules fit together, and where to
    start reading.
    """

    repository_id: str
    summary: str
    architecture: list[str]  # bullet points on how the modules fit together
    entry_points: list[str]
    key_modules: list[str]
    source: str  # "aggregate" | "llm"
    confidence: float
    content_hash: str
    model: str
    created_at: str
    updated_at: str
