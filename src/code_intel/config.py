"""Runtime configuration.

Every tunable is resolved here so nothing is hardcoded at call sites. Values
come from explicit arguments first, then environment variables, then defaults.
The LLM-related settings are declared now (so the shape is stable) but are only
consumed by later phases; Phase 1 uses only the storage and scan settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Directory created inside a target repository to hold its knowledge base.
DATA_DIR_NAME = ".code-intel"
DEFAULT_DB_FILENAME = "index.db"

# Default cap for a single file we are willing to read into memory for hashing
# and (later) parsing. Larger files are recorded in the manifest but skipped.
DEFAULT_MAX_FILE_BYTES = 5_000_000

# Directory names never worth scanning. Kept deliberately small; .gitignore
# handles project-specific exclusions.
DEFAULT_IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        DATA_DIR_NAME,
        "node_modules",
        "vendor",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        ".idea",
        ".vscode",
        "coverage",
        ".gradle",
    }
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name!r} must be an integer, got {raw!r}") from exc


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return raw if raw and raw.strip() else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name!r} must be a float, got {raw!r}") from exc


@dataclass(frozen=True)
class ScanSettings:
    """Controls repository traversal and file filtering."""

    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
    ignored_dirs: frozenset[str] = DEFAULT_IGNORED_DIRS
    respect_gitignore: bool = True


@dataclass(frozen=True)
class LLMSettings:
    """OpenAI-compatible client settings. Consumed by later phases only.

    Declared here so no downstream code invents its own configuration surface.
    Never hardcode these at a call site.
    """

    base_url: str = "http://localhost:5000/v1"
    api_key: str = "not-needed-for-local"
    model: str = "local-model"
    temperature: float = 0.0
    max_tokens: int = 1024
    request_timeout_s: float = 120.0
    max_retries: int = 3
    batch_size: int = 8
    max_concurrency: int = 4

    @classmethod
    def from_env(cls) -> LLMSettings:
        """Build LLM settings from ``CODE_INTEL_LLM_*`` environment variables."""
        defaults = cls()
        return cls(
            base_url=_env_str("CODE_INTEL_LLM_BASE_URL", defaults.base_url),
            api_key=_env_str("CODE_INTEL_LLM_API_KEY", defaults.api_key),
            model=_env_str("CODE_INTEL_LLM_MODEL", defaults.model),
            temperature=_env_float("CODE_INTEL_LLM_TEMPERATURE", defaults.temperature),
            max_tokens=_env_int("CODE_INTEL_LLM_MAX_TOKENS", defaults.max_tokens),
            request_timeout_s=_env_float("CODE_INTEL_LLM_TIMEOUT", defaults.request_timeout_s),
            max_retries=_env_int("CODE_INTEL_LLM_MAX_RETRIES", defaults.max_retries),
            batch_size=_env_int("CODE_INTEL_LLM_BATCH_SIZE", defaults.batch_size),
            max_concurrency=_env_int("CODE_INTEL_LLM_CONCURRENCY", defaults.max_concurrency),
        )


@dataclass(frozen=True)
class Settings:
    """Top-level configuration for a single indexing target."""

    db_path: Path
    scan: ScanSettings = field(default_factory=ScanSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)

    @classmethod
    def for_repository(cls, repo_path: Path, db_path: Path | None = None) -> Settings:
        """Build settings for indexing ``repo_path``.

        The knowledge base lives at ``<repo>/.code-intel/index.db`` by default.
        An explicit ``db_path`` argument wins; otherwise ``CODE_INTEL_DB`` is
        consulted before falling back to the in-repo default.
        """
        resolved_db = db_path
        if resolved_db is None:
            env_db = os.environ.get("CODE_INTEL_DB")
            if env_db and env_db.strip():
                resolved_db = Path(env_db).expanduser()
            else:
                resolved_db = repo_path / DATA_DIR_NAME / DEFAULT_DB_FILENAME

        scan = ScanSettings(
            max_file_bytes=_env_int("CODE_INTEL_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES),
        )
        return cls(db_path=resolved_db.resolve(), scan=scan, llm=LLMSettings.from_env())
