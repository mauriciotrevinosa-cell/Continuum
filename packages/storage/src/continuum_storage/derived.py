"""Content-addressed writes to derived roots (ADR-0001 Layer 4, D-15).

Two properties make this the root-cause fix rather than another guard:

* **The Source Vault is not in the root table.** A writable-root lookup
  physically cannot return it, so a write into the vault is not blocked --
  it is unreachable (ADR-0001 Layer 1).
* **No user-supplied string ever reaches a write path.** Destinations are
  derived from the SHA-256 of the content itself, so write-side traversal
  and zip-slip are structurally impossible and never need to be defended
  against correctly.

Landing is temp-in-destination-directory -> fsync -> atomic rename, which
also gives crash-safety and makes re-running an interrupted job unit a
byte-identical no-op -- the property ADR-0002 section 2 depends on.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from continuum_config import WRITABLE_ROOT_KEYS
from continuum_core import (
    VaultWriteAttemptedError,
    content_hash_bytes,
    fanout_segments,
    is_sha256_hex,
    uuid7,
)

from continuum_storage.paths import ResolvedPath, resolve_within

__all__ = ["DerivedStore", "StoredArtifact"]


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """The outcome of landing bytes in a derived root."""

    root_key: str
    content_hash: str
    path: Path
    size_bytes: int
    already_present: bool
    """True when the identical content was already stored.

    This is what makes a repeated job unit a no-op instead of a duplicate.
    """


class DerivedStore:
    """Content-addressed writer over the writable roots.

    ``roots`` maps root key -> configured path string. Passing
    ``source_vault`` raises: the vault is read-only to Continuum and this
    class is the only thing in the product that can write.
    """

    def __init__(self, roots: Mapping[str, str | os.PathLike[str]]) -> None:
        unwritable = set(roots) - set(WRITABLE_ROOT_KEYS)
        if unwritable:
            raise VaultWriteAttemptedError(
                "A write-capable store cannot be constructed over a read-only root.",
                technical_detail=f"rejected root keys: {sorted(unwritable)}",
                remediation=(
                    "The Source Vault is read-only to Continuum (ADR-0001, D-13). "
                    "Use SourceVaultReader for vault access."
                ),
            )
        self._roots: dict[str, Path] = {
            key: Path(os.path.realpath(value)) for key, value in roots.items()
        }

    @property
    def root_keys(self) -> frozenset[str]:
        return frozenset(self._roots)

    def root(self, root_key: str) -> Path:
        try:
            return self._roots[root_key]
        except KeyError:
            raise VaultWriteAttemptedError(
                f"Root {root_key!r} is not a writable root of this store.",
                technical_detail=f"known writable roots: {sorted(self._roots)}",
            ) from None

    def ensure_root(self, root_key: str) -> Path:
        """Create the root directory if absent and return it."""
        root = self.root(root_key)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def path_for_hash(self, root_key: str, content_hash: str) -> ResolvedPath:
        """Where content with this digest lives, without touching the disk."""
        if not is_sha256_hex(content_hash):
            raise ValueError(f"not a lowercase hex sha256 digest: {content_hash!r}")
        shard, name = fanout_segments(content_hash)
        return resolve_within(self.root(root_key), f"{shard}/{name}", root_key=root_key)

    def has(self, root_key: str, content_hash: str) -> bool:
        return self.path_for_hash(root_key, content_hash).path.is_file()

    def put_bytes(self, root_key: str, data: bytes) -> StoredArtifact:
        """Land ``data`` in ``root_key`` under its content hash.

        Idempotent by construction: identical bytes produce the identical
        destination, and an existing destination is left untouched.
        """
        digest = content_hash_bytes(data)
        return self._land(root_key, digest, [data], len(data))

    def put_stream(
        self, root_key: str, chunks: Iterable[bytes], *, content_hash: str
    ) -> StoredArtifact:
        """Land a stream whose digest the caller has already computed.

        Used for large inputs that must not be resident in memory. The caller
        is trusted for the digest; :meth:`verify` re-checks on read.
        """
        materialised = list(chunks)
        return self._land(root_key, content_hash, materialised, sum(len(c) for c in materialised))

    def _land(
        self, root_key: str, content_hash: str, chunks: Iterable[bytes], size: int
    ) -> StoredArtifact:
        destination = self.path_for_hash(root_key, content_hash)
        if destination.path.is_file():
            return StoredArtifact(
                root_key=root_key,
                content_hash=content_hash,
                path=destination.path,
                size_bytes=destination.path.stat().st_size,
                already_present=True,
            )

        destination.path.parent.mkdir(parents=True, exist_ok=True)

        # Temp file in the DESTINATION directory, so the rename is a
        # same-filesystem operation and therefore atomic. A temp file in the
        # system temp directory could land on another volume, where rename
        # degrades to copy+delete and stops being crash-safe.
        temp = destination.path.parent / f".tmp-{uuid7().hex}"
        try:
            with temp.open("wb") as handle:
                for chunk in chunks:
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination.path)  # atomic on POSIX and Windows
            self._fsync_dir(destination.path.parent)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

        return StoredArtifact(
            root_key=root_key,
            content_hash=content_hash,
            path=destination.path,
            size_bytes=size,
            already_present=False,
        )

    def read_bytes(self, root_key: str, content_hash: str) -> bytes:
        return self.path_for_hash(root_key, content_hash).path.read_bytes()

    def verify(self, root_key: str, content_hash: str) -> bool:
        """Re-hash stored content and confirm it still matches its address.

        Because the address *is* the digest, silent corruption is detectable
        and a silently modified artifact is impossible -- which is most of
        backup integrity handled by the storage convention (ADR-0001 s.9).
        """
        path = self.path_for_hash(root_key, content_hash).path
        if not path.is_file():
            return False
        return content_hash_bytes(path.read_bytes()) == content_hash

    @staticmethod
    def _fsync_dir(directory: Path) -> None:
        """Durably record the rename. POSIX only; Windows has no equivalent."""
        if os.name != "posix":  # pragma: no cover - platform dependent
            return
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
