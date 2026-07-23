"""Content hashing and binary detection.

A file is read exactly once. Binary detection uses the presence of a NUL byte
in the leading window, which is the same cheap heuristic git uses. The hash is
BLAKE2b (fast, 128-bit digest is plenty for change detection).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

_READ_CHUNK = 65_536
_BINARY_SNIFF_BYTES = 8_192
_DIGEST_SIZE = 16  # 128-bit hex digest


@dataclass(frozen=True)
class FileProbe:
    """Result of inspecting a file's bytes."""

    size_bytes: int
    is_binary: bool
    hash: str | None  # None when skipped (binary or over the size cap)


def probe_file(path: Path, max_bytes: int) -> FileProbe:
    """Inspect ``path``: detect binary content and hash it if eligible.

    Files over ``max_bytes`` or containing NUL bytes are not hashed; their
    ``hash`` is ``None`` so callers can record-and-skip.
    """
    size = path.stat().st_size
    if size > max_bytes:
        return FileProbe(size_bytes=size, is_binary=False, hash=None)

    hasher = hashlib.blake2b(digest_size=_DIGEST_SIZE)
    is_binary = False
    seen_bytes = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_READ_CHUNK)
            if not chunk:
                break
            if not is_binary and seen_bytes < _BINARY_SNIFF_BYTES and b"\x00" in chunk:
                is_binary = True
            seen_bytes += len(chunk)
            hasher.update(chunk)

    if is_binary:
        return FileProbe(size_bytes=size, is_binary=True, hash=None)
    return FileProbe(size_bytes=size, is_binary=False, hash=hasher.hexdigest())
