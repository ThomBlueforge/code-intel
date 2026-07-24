"""Design-pattern and class anti-pattern detection (Phase 21).

Structural + naming heuristics over the deterministic symbol set. These are
deliberately conservative and reported with modest confidence — naming is a
signal, not proof. All findings here are ``STATIC_ANALYSIS`` (no LLM).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from code_intel.models import Symbol

# class-name pattern → (label, confidence, required-method matcher | None).
# When a matcher is given, the pattern is reported only if the class actually has
# a method matching it: a class merely *named* like a pattern (e.g. a `Repository`
# data model with no data-access methods) is not the pattern and must not match.
_NAME_PATTERNS: tuple[tuple[re.Pattern[str], str, float, re.Pattern[str] | None], ...] = (
    (
        re.compile(r"(Repository|Repo|Store|Dao)$"),
        "Repository",
        0.6,
        re.compile(
            r"^(find|get|list|all|load|fetch|query|save|insert|create|update|"
            r"upsert|delete|remove|exists|count|by_)",
            re.IGNORECASE,
        ),
    ),
    (re.compile(r"Factory$"), "Factory", 0.6,
     re.compile(r"^(create|make|build|new|from_|of|produce)", re.IGNORECASE)),
    (re.compile(r"Builder$"), "Builder", 0.6,
     re.compile(r"^(build|with_|set_|add|append)", re.IGNORECASE)),
    (re.compile(r"Strategy$"), "Strategy", 0.55, None),
    (re.compile(r"Adapter$"), "Adapter", 0.55, None),
    (re.compile(r"(Observer|Listener)$"), "Observer", 0.5, None),
    (re.compile(r"(Facade)$"), "Facade", 0.5, None),
    (re.compile(r"(Service)$"), "Service", 0.5, None),
)
_SINGLETON_METHODS = frozenset({"get_instance", "getinstance", "instance", "shared"})
_UTILITY_NAMES = re.compile(r"(Utils?|Helpers?|Common|Misc)$")
# Interfaces/protocols/ABCs are expected to declare many methods; a high method
# count on them is not a "large class" smell.
_INTERFACE_LIKE = re.compile(r"\b(Protocol|ABC|ABCMeta|Interface)\b")

_GOD_OBJECT_METHODS = 15
_GOD_OBJECT_LOC = 300
_LARGE_CLASS_METHODS = 12
_UTILITY_METHOD_MIN = 5


@dataclass(frozen=True)
class DetectedPattern:
    """A detected design pattern or class anti-pattern (pre-persistence)."""

    category: str  # "design_pattern" | "god_object" | "large_class" | "utility_abuse"
    title: str
    detail: str
    confidence: float
    target: str


class PatternDetector:
    """Detects patterns and class-level anti-patterns from symbols."""

    def detect(
        self, symbols: list[Symbol], children_by_parent: dict[str, list[Symbol]]
    ) -> list[DetectedPattern]:
        found: list[DetectedPattern] = []
        for symbol in symbols:
            if symbol.type not in ("class", "struct", "interface"):
                continue
            methods = [c for c in children_by_parent.get(symbol.id, []) if c.type == "method"]
            found.extend(self._for_class(symbol, methods))
        return found

    def _for_class(self, symbol: Symbol, methods: list[Symbol]) -> list[DetectedPattern]:
        out: list[DetectedPattern] = []
        loc = symbol.end_line - symbol.start_line + 1
        where = f"{symbol.path}:{symbol.start_line}"

        for pattern, label, confidence, method_re in _NAME_PATTERNS:
            if not pattern.search(symbol.name):
                continue
            if method_re is not None and not any(method_re.match(m.name) for m in methods):
                continue  # named like the pattern but lacks its characteristic methods
            out.append(
                DetectedPattern(
                    "design_pattern",
                    f"{label} pattern: {symbol.name}",
                    f"`{symbol.name}` at {where} matches the {label} pattern "
                    f"(name + characteristic methods).",
                    confidence,
                    symbol.name,
                )
            )
            break

        if any(m.name.lower() in _SINGLETON_METHODS for m in methods):
            out.append(
                DetectedPattern(
                    "design_pattern",
                    f"Singleton pattern: {symbol.name}",
                    f"`{symbol.name}` exposes an instance accessor at {where}.",
                    0.6,
                    symbol.name,
                )
            )

        if len(methods) >= _GOD_OBJECT_METHODS or loc >= _GOD_OBJECT_LOC:
            out.append(
                DetectedPattern(
                    "god_object",
                    f"God object: {symbol.name}",
                    f"`{symbol.name}` has {len(methods)} methods over {loc} lines at {where}.",
                    0.7,
                    symbol.name,
                )
            )
        elif len(methods) >= _LARGE_CLASS_METHODS and not _INTERFACE_LIKE.search(symbol.signature):
            out.append(
                DetectedPattern(
                    "large_class",
                    f"Large class: {symbol.name}",
                    f"`{symbol.name}` has {len(methods)} methods at {where}.",
                    0.55,
                    symbol.name,
                )
            )

        if _UTILITY_NAMES.search(symbol.name) and len(methods) >= _UTILITY_METHOD_MIN:
            out.append(
                DetectedPattern(
                    "utility_abuse",
                    f"Utility class abuse: {symbol.name}",
                    f"`{symbol.name}` collects {len(methods)} loosely-related methods at {where}.",
                    0.5,
                    symbol.name,
                )
            )
        return out
