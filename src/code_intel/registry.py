"""User-level registry of indexed repositories.

Each repository's knowledge base lives at ``<repo>/.code-intel/index.db``, so no
single database lists every indexed repo. This small JSON registry — by default
``~/.code-intel/registry.json``, overridable via ``CODE_INTEL_REGISTRY`` — records
which repositories have been indexed so the browser UI can list them without the
user re-typing paths.

It holds convenience metadata only. It is never a source of truth for facts
(SQLite remains that) and can be deleted and rebuilt by re-indexing.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from code_intel.config import DATA_DIR_NAME
from code_intel.models import utc_now_iso

DEFAULT_REGISTRY_FILENAME = "registry.json"


@dataclass(frozen=True)
class RegistryEntry:
    """One indexed repository, as remembered for the UI's repo picker."""

    path: str  # resolved absolute repository path
    name: str
    db_path: str  # resolved absolute path to the repo's index.db
    last_indexed: str  # ISO-8601 UTC

    def to_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "name": self.name,
            "db_path": self.db_path,
            "last_indexed": self.last_indexed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> RegistryEntry:
        return cls(
            path=data["path"],
            name=data["name"],
            db_path=data["db_path"],
            last_indexed=data["last_indexed"],
        )


def default_registry_path() -> Path:
    """Resolve the registry file location (env override, else user home)."""
    override = os.environ.get("CODE_INTEL_REGISTRY")
    if override and override.strip():
        return Path(override).expanduser().resolve()
    return (Path.home() / DATA_DIR_NAME / DEFAULT_REGISTRY_FILENAME).resolve()


class RepositoryRegistry:
    """Reads and writes the JSON registry of indexed repositories."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_registry_path()

    @property
    def path(self) -> Path:
        return self._path

    def list(self) -> list[RegistryEntry]:
        """All known entries, most recently indexed first."""
        entries = self._load()
        return sorted(entries.values(), key=lambda e: e.last_indexed, reverse=True)

    def get(self, repo_path: Path) -> RegistryEntry | None:
        return self._load().get(str(repo_path.resolve()))

    def record(self, *, repo_path: Path, name: str, db_path: Path) -> RegistryEntry:
        """Remember (or refresh) a repository as indexed just now."""
        entries = self._load()
        key = str(repo_path.resolve())
        entry = RegistryEntry(
            path=key,
            name=name,
            db_path=str(db_path.resolve()),
            last_indexed=utc_now_iso(),
        )
        entries[key] = entry
        self._save(entries)
        return entry

    def remove(self, repo_path: Path) -> bool:
        """Forget a repository. Returns whether an entry was removed."""
        entries = self._load()
        key = str(repo_path.resolve())
        if key not in entries:
            return False
        del entries[key]
        self._save(entries)
        return True

    def _load(self) -> dict[str, RegistryEntry]:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        result: dict[str, RegistryEntry] = {}
        repositories = data.get("repositories", {})
        if not isinstance(repositories, dict):
            return {}
        for key, value in repositories.items():
            if not isinstance(value, dict):
                continue
            try:
                result[key] = RegistryEntry.from_dict(value)
            except KeyError:
                continue
        return result

    def _save(self, entries: dict[str, RegistryEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"repositories": {k: e.to_dict() for k, e in entries.items()}}
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)
