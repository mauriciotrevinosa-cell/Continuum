"""Content addressing (D-15 / ADR-0001 section 4, ADR-0005 section 4).

One convention delivers deduplication, atomic and crash-safe writes,
corruption detection, safe job re-runs and backup integrity. Hashing is
streaming rather than whole-file-in-memory because OQ-3 fixes the Source
Vault at "hundreds of GB or multiple TB".

This module is pure computation. It never opens a file -- ``continuum_storage``
owns filesystem access (ADR-0001 Layer 3) and feeds chunks in.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

__all__ = [
    "CHUNK_BYTES",
    "FANOUT",
    "content_hash_bytes",
    "content_hash_stream",
    "fanout_segments",
    "is_sha256_hex",
]

#: Read size for streaming hashes. 1 MiB balances syscall overhead against
#: resident memory for multi-gigabyte video assets.
CHUNK_BYTES = 1024 * 1024

#: Number of leading hex characters used as a directory shard, so a single
#: directory never accumulates millions of entries.
FANOUT = 2

_SHA256_HEX_LEN = 64


def content_hash_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def content_hash_stream(chunks: Iterable[bytes]) -> str:
    """Return the lowercase hex SHA-256 of a stream of chunks.

    Accepts any iterable so the caller controls how bytes are produced --
    a file read loop, a network stream, or a synthetic generator in tests.
    """
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def is_sha256_hex(value: str) -> bool:
    """True if ``value`` is a well-formed lowercase hex SHA-256 digest."""
    if len(value) != _SHA256_HEX_LEN:
        return False
    return all(c in "0123456789abcdef" for c in value)


def fanout_segments(content_hash: str) -> tuple[str, str]:
    """Split a digest into ``(shard, filename)`` for content-addressed storage.

    ``fanout_segments("ab12...") -> ("ab", "ab12...")``

    The full digest is kept as the filename so a file is self-identifying
    even if it is copied out of its shard directory.
    """
    if not is_sha256_hex(content_hash):
        raise ValueError(f"not a lowercase hex sha256 digest: {content_hash!r}")
    return content_hash[:FANOUT], content_hash
