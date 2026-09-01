"""Source Vault reader (ADR-0001 Layer 1, FOUNDATION_APPROVAL A-01, OQ-5).

``SourceVaultReader`` exposes read operations and nothing else. There is no
``write``, ``delete``, ``rename``, ``mkdir``, ``touch`` or ``open_write``
method -- not a disabled one, not one that raises. A write to the vault is
not *forbidden*; it is **unrepresentable**.

That distinction is the whole point. A guard is something a future
contributor -- human or agent -- can be argued past when a feature is
inconvenient. A missing method cannot be called.

There is deliberately no escape hatch of any kind (D-13 / OQ-5): no force
flag, no admin mode, no "cleanup" path, no temporary write capability. If a
future requirement genuinely needs Continuum-managed source mutation, that
is a new architecture decision, not a parameter.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import IO

from continuum_core import CHUNK_BYTES, content_hash_stream

from continuum_storage.paths import ResolvedPath, resolve_within, same_file_as

__all__ = ["SourceVaultReader", "VaultEntry"]


@dataclass(frozen=True, slots=True)
class VaultEntry:
    """One entry observed in the vault. A description, not a handle."""

    relative: PurePath
    is_dir: bool
    is_file: bool
    is_symlink: bool
    size_bytes: int
    modified_ns: int


class SourceVaultReader:
    """Read-only access to one Source Vault root.

    Every public method is a read. Adding a mutating method to this class is
    a Phase 0 invariant violation and is asserted against by
    ``tests/acceptance/test_110_05_vault_readonly.py``.
    """

    #: Names that must never be treated as vault content. Cloud-sync clients
    #: write these into folders they manage; a scanner that ingested them
    #: would create phantom assets (F-13).
    IGNORED_NAMES = frozenset(
        {".ds_store", "thumbs.db", "desktop.ini", ".dropbox", ".dropbox.attr"}
    )

    def __init__(self, root: str | os.PathLike[str], *, root_key: str = "source_vault") -> None:
        self._root = Path(os.path.realpath(root))
        self._root_key = root_key

    @property
    def root(self) -> Path:
        return self._root

    @property
    def root_key(self) -> str:
        return self._root_key

    def exists(self) -> bool:
        """Whether the configured vault root is present.

        A missing vault is normal, not an error: OQ-3 anticipates an external
        or temporarily disconnected disk. Callers degrade to OFFLINE rather
        than deleting derived records.
        """
        return self._root.is_dir()

    def resolve(self, relative: str | PurePath) -> ResolvedPath:
        """Validate and resolve a vault-relative path."""
        return resolve_within(self._root, relative, root_key=self._root_key)

    def stat(self, relative: str | PurePath) -> os.stat_result:
        """``stat`` one vault entry."""
        return self.resolve(relative).path.stat()

    def entry(self, relative: str | PurePath) -> VaultEntry:
        """Describe one vault entry without opening it."""
        resolved = self.resolve(relative)
        info = resolved.path.lstat()
        return VaultEntry(
            relative=resolved.relative,
            is_dir=resolved.path.is_dir(),
            is_file=resolved.path.is_file(),
            is_symlink=resolved.path.is_symlink(),
            size_bytes=info.st_size,
            modified_ns=info.st_mtime_ns,
        )

    def iter_entries(
        self, relative: str | PurePath = "", *, recursive: bool = False
    ) -> Iterator[VaultEntry]:
        """Iterate vault entries beneath ``relative``.

        Entries that resolve outside the root -- a symlink or junction
        pointing elsewhere -- are skipped rather than raising, so one hostile
        link cannot abort a scan of an otherwise healthy vault. Skips are the
        caller's business to log.
        """
        base = self._root if str(relative) in ("", ".") else self.resolve(relative).path
        if not base.is_dir():
            return

        stack = [base]
        while stack:
            current = stack.pop()
            try:
                children = sorted(current.iterdir())
            except OSError:
                continue
            for child in children:
                if child.name.lower() in self.IGNORED_NAMES:
                    continue
                try:
                    rel = child.resolve().relative_to(self._root)
                except (OSError, ValueError):
                    # Escaping link, or a path we cannot resolve. Skip it.
                    continue
                try:
                    info = child.lstat()
                    is_dir = child.is_dir()
                    yield VaultEntry(
                        relative=PurePath(rel),
                        is_dir=is_dir,
                        is_file=child.is_file(),
                        is_symlink=child.is_symlink(),
                        size_bytes=info.st_size,
                        modified_ns=info.st_mtime_ns,
                    )
                except OSError:
                    continue
                else:
                    if recursive and is_dir and not child.is_symlink():
                        stack.append(child)

    def open_read(self, relative: str | PurePath) -> IO[bytes]:
        """Open a vault file for binary reading.

        Opened ``rb`` and then re-verified against the resolved target by
        descriptor identity, so a path swapped between validation and open is
        detected rather than read.
        """
        resolved = self.resolve(relative)
        handle = resolved.path.open("rb")
        try:
            if not same_file_as(handle.fileno(), resolved.path):
                raise OSError(f"file changed identity between validation and open: {resolved.path}")
        except Exception:
            handle.close()
            raise
        return handle

    def read_bytes(self, relative: str | PurePath, *, limit: int | None = None) -> bytes:
        """Read a whole vault file, optionally capped at ``limit`` bytes."""
        with self.open_read(relative) as handle:
            return handle.read() if limit is None else handle.read(limit)

    def content_hash(self, relative: str | PurePath) -> str:
        """Stream a vault file and return its SHA-256.

        Streaming rather than whole-file-in-memory because OQ-3 fixes the
        vault at "hundreds of GB or multiple TB": a multi-gigabyte video must
        not be resident to be hashed.
        """
        with self.open_read(relative) as handle:
            return content_hash_stream(iter(lambda: handle.read(CHUNK_BYTES), b""))
