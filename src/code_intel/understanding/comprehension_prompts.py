"""Prompts for the file- and repo-level comprehension passes (Phase 23).

The model is never shown raw source here — it is shown the *understandings of the
level below* (symbol summaries for a file pass, file summaries for the repo
pass). This keeps every level grounded in already-verified facts and keeps token
cost bounded and roughly linear in the number of symbols and files.
"""

from __future__ import annotations

from code_intel.llm.client import ChatMessage

_FILE_SYSTEM = (
    "You are a precise software architect describing a source file from the "
    "already-analysed understanding of its parts. Answer ONLY with a single JSON "
    "object, no prose, no markdown fences. Do not invent behaviour that is not "
    "supported by the provided units; when unsure, keep it short and lower the "
    "confidence."
)

_FILE_TEMPLATE = """File: `{path}`

Top-level units in this file (each with what it does):
{units}

This file collaborates with: {collaborators}

Describe what THIS FILE does as a whole. Return JSON with exactly these keys:
- "summary": 1-3 sentences — what the file is for and its role in the system.
- "responsibilities": array of short phrases, one per distinct thing the file
  does (its enumerated responsibilities, e.g. "Parse config from the environment").
- "key_exports": array of the names other modules would import from here.
- "role": a short architectural role phrase (e.g. "HTTP routing", "SQLite storage").
- "confidence": float in [0,1]."""

_REPO_SYSTEM = (
    "You are a staff engineer writing the orientation a new contributor (or an "
    "AI agent) would read first. Answer ONLY with a single JSON object, no prose, "
    "no markdown fences. Ground every statement in the provided files; when "
    "unsure, be brief and lower the confidence."
)

_REPO_TEMPLATE = """Repository: `{name}`

Files, each with its role and one-line understanding:
{files}

Known entry points (static analysis): {entry_points}

Give a high-level architectural overview. Return JSON with exactly these keys:
- "summary": a short paragraph — what this project is and what it does.
- "architecture": array of bullet strings — how the modules fit together (layers,
  data flow, key boundaries).
- "confidence": float in [0,1]."""

_MAX_UNITS = 40
_MAX_FILES = 120


def build_file_messages(
    path: str, responsibilities: list[str], collaborators: list[str]
) -> list[ChatMessage]:
    units = "\n".join(f"- {r}" for r in responsibilities[:_MAX_UNITS]) or "- (none)"
    collab = ", ".join(collaborators) if collaborators else "(none detected)"
    user = _FILE_TEMPLATE.format(path=path, units=units, collaborators=collab)
    return [
        ChatMessage(role="system", content=_FILE_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def build_repo_messages(
    name: str, files: list[tuple[str, str, str]], entry_points: list[str]
) -> list[ChatMessage]:
    listing = "\n".join(
        f"- `{path}` [{role}]: {summary}" for path, role, summary in files[:_MAX_FILES]
    ) or "- (none)"
    eps = ", ".join(entry_points) if entry_points else "(none detected)"
    user = _REPO_TEMPLATE.format(name=name, files=listing, entry_points=eps)
    return [
        ChatMessage(role="system", content=_REPO_SYSTEM),
        ChatMessage(role="user", content=user),
    ]
