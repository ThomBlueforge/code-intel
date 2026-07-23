"""Language detection by filename.

A file whose language cannot be identified here is not part of the code
knowledge base and is skipped during ingestion. The mapping is intentionally
closed: extend it deliberately rather than guessing at unknown extensions.
"""

from __future__ import annotations

from pathlib import Path

# Extension (lowercase, including dot) -> canonical language name.
_EXTENSION_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".cs": "C#",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".c": "C",
    ".h": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".sql": "SQL",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
}

# Exact filenames (no useful extension) mapped to a language.
_FILENAME_LANGUAGE: dict[str, str] = {
    "dockerfile": "Dockerfile",
    "makefile": "Makefile",
}


def detect_language(path: Path) -> str | None:
    """Return the canonical language for ``path`` or ``None`` if unknown."""
    suffix = path.suffix.lower()
    if suffix in _EXTENSION_LANGUAGE:
        return _EXTENSION_LANGUAGE[suffix]
    return _FILENAME_LANGUAGE.get(path.name.lower())


def supported_languages() -> frozenset[str]:
    """All languages the ingestion layer can currently recognise."""
    return frozenset(_EXTENSION_LANGUAGE.values()) | frozenset(_FILENAME_LANGUAGE.values())
