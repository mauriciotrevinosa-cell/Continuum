"""Videos inside compressed archives, extracted on demand into a bounded cache.

Every video member of the real anime archives is DEFLATE-compressed, so it
cannot be streamed or seeked in place. Playing one needs its bytes as a plain
file. This module provides exactly that, and nothing more:

* **on demand only** - one member at a time, when someone asks to watch it;
  nothing is extracted by a scan, and nothing is ever written into the Vault;
* **content-addressed** - a member lands at ``cache/archive-members/<shard>/<sha256>``,
  so two archives holding the same episode share one copy and a repeated
  extraction is a no-op;
* **verified** - the archive's CRC-32 is checked by the reader at the end of
  the member, and the size must match the central directory;
* **bounded** - a byte budget; least recently used members are evicted first.
  Eviction deletes only Continuum's own cached copies, never a source file.

The member to extract is named by the catalog (an archive relative to a
catalog root, and an entry name recorded from its central directory), never by
a request.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
import zipfile
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import PurePath

from continuum_core import ContinuumError, ErrorCategory, PathEscapesRootError, is_sha256_hex, uuid7

from continuum_storage.derived import DerivedStore
from continuum_storage.paths import ResolvedPath, resolve_within
from continuum_storage.sources import normalized_entry
from continuum_storage.survey import CatalogRoot

__all__ = [
    "CACHE_ROOT",
    "CachedMember",
    "MemberCache",
    "MemberCacheError",
    "MemberUnavailableError",
]

CACHE_ROOT = "cache"
_FOLDER = "archive-members"
_CHUNK = 4 * 1024 * 1024
#: Free space kept on the cache volume beyond the member itself.
_HEADROOM = 512 * 1024 * 1024


class MemberUnavailableError(ContinuumError):
    """The member is not in its archive as catalogued, or the archive changed."""

    code = "catalog.member_unavailable"
    category = ErrorCategory.PERMANENT_INPUT


class MemberCacheError(ContinuumError):
    """The cache cannot take the member (budget or disk space)."""

    code = "catalog.member_cache_full"
    category = ErrorCategory.PERMANENT_CONFIG


@dataclass(frozen=True, slots=True)
class CachedMember:
    sha256: str
    size_bytes: int
    already_present: bool
    evicted: tuple[str, ...] = ()


class MemberCache:
    def __init__(self, derived: DerivedStore, *, budget_bytes: int, max_member_bytes: int) -> None:
        self._derived = derived
        self.budget_bytes = budget_bytes
        self.max_member_bytes = max_member_bytes

    # -- locations ------------------------------------------------------------
    def _folder(self) -> ResolvedPath:
        root = self._derived.ensure_root(CACHE_ROOT)
        return resolve_within(root, _FOLDER, root_key=CACHE_ROOT)

    def _path(self, sha256: str) -> ResolvedPath:
        if not is_sha256_hex(sha256):
            raise ValueError("not a sha256 digest")
        root = self._derived.ensure_root(CACHE_ROOT)
        return resolve_within(root, f"{_FOLDER}/{sha256[:2]}/{sha256}", root_key=CACHE_ROOT)

    def has(self, sha256: str) -> bool:
        try:
            return self._path(sha256).path.is_file()
        except (ValueError, PathEscapesRootError):
            return False

    def size(self, sha256: str) -> int | None:
        try:
            return int(self._path(sha256).path.stat().st_size)
        except (ValueError, PathEscapesRootError, OSError):
            return None

    def usage(self) -> tuple[int, int]:
        """(bytes, members) currently cached."""
        total = count = 0
        for _sha, size, _used in self._entries():
            total += size
            count += 1
        return total, count

    def _entries(self) -> list[tuple[str, int, float]]:
        folder = self._folder().path
        out: list[tuple[str, int, float]] = []
        if not folder.is_dir():
            return out
        for shard in folder.iterdir():
            if not shard.is_dir():
                continue
            for item in shard.iterdir():
                if item.is_file() and is_sha256_hex(item.name):
                    info = item.stat()
                    out.append((item.name, int(info.st_size), float(info.st_mtime)))
        return out

    # -- extraction -----------------------------------------------------------
    def extract(
        self,
        root: CatalogRoot,
        relative: str,
        entry_name: str,
        *,
        expected_size: int,
        expected_crc: int | None,
        known_sha256: str | None = None,
        protect: Collection[str] = (),
    ) -> CachedMember:
        """Extract one member into the cache (or find it there), verified."""
        if known_sha256 and self.has(known_sha256):
            self.touch(known_sha256)
            return CachedMember(known_sha256, int(self.size(known_sha256) or 0), True)
        if expected_size > self.max_member_bytes:
            raise MemberCacheError(
                "This video is larger than the largest member Continuum extracts.",
                remediation="Raise CONTINUUM_MEMBER_CACHE_MAX_MEMBER_BYTES to watch it.",
            )
        if expected_size > self.budget_bytes:
            raise MemberCacheError(
                "This video is larger than the whole member cache budget.",
                remediation="Raise CONTINUUM_MEMBER_CACHE_BYTES to watch it.",
            )
        evicted = self.evict(reserve=expected_size, protect=protect)
        folder = self._folder().path
        folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(folder).free
        if free < expected_size + _HEADROOM:
            raise MemberCacheError(
                "There is not enough free disk space to prepare this video.",
                technical_detail=f"free={free} needed={expected_size + _HEADROOM}",
                remediation="Free some space on the ContinuumData drive, then try again.",
            )
        wanted = normalized_entry(entry_name)
        temp = folder / f".tmp-{uuid7().hex}"
        digest = hashlib.sha256()
        written = 0
        try:
            with (
                root.reader.open_read(PurePath(relative)) as handle,
                zipfile.ZipFile(handle) as archive,
            ):
                matches = [
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and normalized_entry(info.filename) == wanted
                ]
                if wanted is None or len(matches) != 1:
                    raise MemberUnavailableError("That video is no longer in its archive.")
                info = matches[0]
                if info.file_size != expected_size or (
                    expected_crc is not None and info.CRC != expected_crc
                ):
                    raise MemberUnavailableError(
                        "The archive changed since it was catalogued.",
                        remediation="Rescan the Library, then try again.",
                    )
                with archive.open(info) as stream, temp.open("wb") as out:
                    while True:
                        chunk = stream.read(_CHUNK)
                        if not chunk:
                            break
                        written += len(chunk)
                        if written > expected_size:
                            raise MemberUnavailableError(
                                "The video is larger than its archive says."
                            )
                        digest.update(chunk)
                        out.write(chunk)
                    out.flush()
                    os.fsync(out.fileno())
        except MemberUnavailableError:
            temp.unlink(missing_ok=True)
            raise
        except (
            PathEscapesRootError,
            OSError,
            zipfile.BadZipFile,
            RuntimeError,
            NotImplementedError,
        ) as exc:
            temp.unlink(missing_ok=True)
            raise MemberUnavailableError(
                "The video could not be read from its archive.",
                technical_detail=f"{type(exc).__name__}: {exc}",
            ) from None
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        if written != expected_size:
            temp.unlink(missing_ok=True)
            raise MemberUnavailableError(
                "The video in the archive is shorter than its archive says."
            )
        sha = digest.hexdigest()
        destination = self._path(sha)
        destination.path.parent.mkdir(parents=True, exist_ok=True)
        if destination.path.is_file():
            temp.unlink(missing_ok=True)
            self.touch(sha)
            return CachedMember(sha, expected_size, True, evicted)
        os.replace(temp, destination.path)
        return CachedMember(sha, expected_size, False, evicted)

    def touch(self, sha256: str) -> None:
        """Mark a member as just used, for least-recently-used eviction."""
        try:
            now = time.time()
            os.utime(self._path(sha256).path, (now, now))
        except (ValueError, PathEscapesRootError, OSError):
            return

    def evict(self, *, reserve: int = 0, protect: Collection[str] = ()) -> tuple[str, ...]:
        """Remove least recently used members until ``reserve`` more bytes fit the budget."""
        entries = sorted(self._entries(), key=lambda e: e[2])
        total = sum(size for _sha, size, _used in entries)
        removed: list[str] = []
        for sha, size, _used in entries:
            if total + reserve <= self.budget_bytes:
                break
            if sha in protect:
                continue
            try:
                self._path(sha).path.unlink()
            except OSError:
                continue
            total -= size
            removed.append(sha)
        return tuple(removed)

    # -- reading --------------------------------------------------------------
    def open_range(
        self, sha256: str, start: int = 0, end: int | None = None, *, chunk: int = 1 << 20
    ) -> tuple[int, int, int, Iterator[bytes]]:
        """(size, first, last, body) for bytes ``start``..``end`` of a cached member."""
        path = self._path(sha256).path
        handle = path.open("rb")
        try:
            size = os.fstat(handle.fileno()).st_size
        except OSError:
            handle.close()
            raise
        last = size - 1 if end is None else min(end, size - 1)
        if start < 0 or start > last:
            handle.close()
            raise ValueError("requested range is not satisfiable")
        self.touch(sha256)

        def body() -> Iterator[bytes]:
            try:
                handle.seek(start)
                remaining = last - start + 1
                while remaining > 0:
                    data = handle.read(min(chunk, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
            finally:
                handle.close()

        return size, start, last, body()
