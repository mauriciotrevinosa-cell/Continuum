"""Read-only access to held media, addressed by opaque identifiers.

A viewer must be able to open what the Library holds without the browser
ever naming a file. The contract, end to end:

1. The acquisition engine's scan lists every file in the Vault
   (``vault-index.json``), relative to the Vault root.
2. This module turns each listed file into an **opaque media id** - a keyed
   digest of its relative path. The id is stable across scans and carries no
   path information.
3. A request presents an id. The id is looked up in the index (so only files
   the scan actually saw can be addressed), and the relative path it maps to
   is resolved through :class:`SourceVaultReader` - the single hardened
   resolver, with traversal, UNC, drive, device-name and symlink/junction
   escape checks - against the **configured** Source Vault root.
4. Bytes are read, never written.

Nothing here accepts a path from a caller (F-50). An id that is malformed,
unknown, stale, or maps outside the Vault is refused the same way: not found.

Archives are containers. Their pages (images) are addressed by position in
the archive's own sorted listing, never by the entry name, and are read into
memory one at a time with a size cap. Nothing is ever extracted to disk.
Video inside an archive is listed but not streamed: compressed entries are not
seekable, and a player without seeking is not a player.
"""

from __future__ import annotations

import hashlib
import os
import re
import zipfile
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import IO, Any

from continuum_core import PathEscapesRootError

from continuum_storage.acquisition import AcquisitionStore
from continuum_storage.vault import SourceVaultReader

__all__ = [
    "MEDIA_ID_PATTERN",
    "ArchiveListing",
    "ArchivePage",
    "MediaFile",
    "MediaLibrary",
    "MediaUnavailableError",
    "media_id_for",
]

#: What an id looks like. Checked before any lookup, so a hostile string never
#: reaches the index, let alone the filesystem.
MEDIA_ID_PATTERN = r"^m1_[0-9a-f]{32}$"
_MEDIA_ID = re.compile(MEDIA_ID_PATTERN)

#: The largest single page read into memory. Real pages are far smaller; a
#: bigger entry is refused rather than streamed out of a compressed archive.
MAX_PAGE_BYTES = 40 * 1024 * 1024
#: How many archive listings stay parsed in memory.
LISTING_CACHE_SIZE = 64

VIDEO_TYPES: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".ts": "video/mp2t",
}
#: ".ts" is also TypeScript. A contained ".ts" is footage only when it is not a
#: declaration file and is large enough to be video; source files are kilobytes.
MIN_TRANSPORT_STREAM_BYTES = 512 * 1024
IMAGE_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
}
DOCUMENT_TYPES: dict[str, str] = {".pdf": "application/pdf"}
ARCHIVE_EXTENSIONS = frozenset({".zip", ".cbz"})

_NATURAL = re.compile(r"(\d+)")


def media_id_for(relative: str) -> str:
    """The opaque, stable id of a Vault-relative path.

    Normalised to forward slashes first, so the same file has the same id
    whichever platform produced the index.
    """
    normal = relative.replace("\\", "/")
    digest = hashlib.sha256(f"continuum-media/1\x00{normal}".encode()).hexdigest()
    return f"m1_{digest[:32]}"


def _natural_key(text: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in _NATURAL.split(text)]


class MediaUnavailableError(LookupError):
    """The id does not name viewable media. Deliberately uninformative."""


@dataclass(frozen=True, slots=True)
class MediaFile:
    """One held file, described without exposing where it lives."""

    id: str
    name: str
    extension: str
    kind: str
    size_bytes: int
    content_type: str | None
    #: "pages" (image archive), "video", "document", "bundle" (archive of
    #: videos), or "none".
    view: str
    archive_images: int = 0
    archive_videos: int = 0
    archive_video_entries: tuple[dict[str, Any], ...] = ()
    relative: str = field(default="", repr=False)


@dataclass(frozen=True, slots=True)
class ArchivePage:
    index: int
    label: str
    chapter: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ArchiveListing:
    pages: tuple[ArchivePage, ...]
    #: (label, first page index, page count), in reading order.
    chapters: tuple[tuple[str, int, int], ...]
    videos: tuple[dict[str, Any], ...]
    other_entries: int


class MediaLibrary:
    """Opaque-id access to the media the acquisition scan has seen."""

    def __init__(self, store: AcquisitionStore, vault_root: str) -> None:
        self._store = store
        self._vault_root = vault_root
        self._reader = SourceVaultReader(vault_root) if vault_root else None
        self._ids: dict[str, str] = {}
        self._ids_for: tuple[str, int] | None = None
        self._listings: OrderedDict[tuple[str, int, int], ArchiveListing] = OrderedDict()

    # -- availability -------------------------------------------------------
    def status(self) -> tuple[bool, str]:
        """Whether held media can be opened, and if not, why - in plain words."""
        index = self._store.read("vault-index.json")
        if not index:
            return False, "The Library has not been scanned yet."
        if self._reader is None or not self._reader.exists():
            return False, "The Source Vault is not configured or not reachable on this machine."
        scanned = str(index.get("vault_root") or "")
        if not scanned or not _same_location(scanned, str(self._reader.root)):
            return (
                False,
                "The Library was scanned from a different folder than the configured Source Vault.",
            )
        return True, ""

    # -- lookup -------------------------------------------------------------
    def _index(self) -> tuple[dict[str, Any], tuple[str, int]]:
        index = self._store.read("vault-index.json") or {}
        files = index.get("files")
        files = files if isinstance(files, dict) else {}
        return files, (str(index.get("generated_at") or ""), len(files))

    def _index_files(self) -> dict[str, Any]:
        return self._index()[0]

    def _lookup(self, media_id: str) -> tuple[str, dict[str, Any]]:
        if not isinstance(media_id, str) or not _MEDIA_ID.match(media_id):
            raise MediaUnavailableError(media_id)
        ok, _reason = self.status()
        if not ok:
            raise MediaUnavailableError(media_id)
        files, marker = self._index()
        if self._ids_for != marker:
            self._ids = {media_id_for(rel): rel for rel in files}
            self._ids_for = marker
        rel = self._ids.get(media_id)
        record = files.get(rel) if rel is not None else None
        if rel is None or not isinstance(record, dict) or not self._inside(rel):
            raise MediaUnavailableError(media_id)
        return rel, record

    def _inside(self, rel: str) -> bool:
        """Whether an index entry resolves to a file inside the configured Vault.

        The index is a document; a document can be wrong, tampered with, or
        simply older than the Vault. An entry that names a traversal, an
        absolute path, a link leading out of the Vault, or a file removed since
        the scan is treated as if it did not exist - not described, not opened.
        """
        if self._reader is None:
            return False
        try:
            return self._reader.resolve(PurePath(rel)).path.is_file()
        except (PathEscapesRootError, OSError, ValueError):
            return False

    def describe(self, media_id: str) -> MediaFile:
        rel, record = self._lookup(media_id)
        return _describe(media_id, rel, record)

    def describe_relative(self, relative: str) -> MediaFile | None:
        """Describe a file named by the engine's documents (never by a request)."""
        files = self._index_files()
        record = files.get(relative)
        if not isinstance(record, dict) or not self._inside(relative):
            return None
        return _describe(media_id_for(relative), relative, record)

    # -- reading ------------------------------------------------------------
    def _open(self, rel: str) -> IO[bytes]:
        assert self._reader is not None  # status() was checked by _lookup
        try:
            return self._reader.open_read(PurePath(rel))
        except (PathEscapesRootError, OSError) as exc:
            raise MediaUnavailableError(rel) from exc

    def open_range(
        self, media_id: str, start: int = 0, end: int | None = None, *, chunk: int = 1 << 20
    ) -> tuple[MediaFile, int, int, Iterator[bytes]]:
        """Stream bytes ``start``..``end`` (inclusive) of a video or document.

        Returns the descriptor, the resolved start and end, and an iterator
        that owns and closes the file handle.
        """
        media = self.describe(media_id)
        if media.view not in ("video", "document"):
            raise MediaUnavailableError(media_id)
        rel, _record = self._lookup(media_id)
        handle = self._open(rel)
        try:
            size = os.fstat(handle.fileno()).st_size
        except OSError as exc:
            handle.close()
            raise MediaUnavailableError(media_id) from exc
        last = size - 1 if end is None else min(end, size - 1)
        if start < 0 or start > last:
            handle.close()
            raise ValueError("requested range is not satisfiable")

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

        return media, start, last, body()

    def archive_listing(self, media_id: str) -> ArchiveListing:
        media = self.describe(media_id)
        if media.view not in ("pages", "bundle"):
            raise MediaUnavailableError(media_id)
        rel, record = self._lookup(media_id)
        key = (media_id, int(record.get("size") or 0), int(record.get("mtime_ns") or 0))
        cached = self._listings.get(key)
        if cached is not None:
            self._listings.move_to_end(key)
            return cached
        with self._open(rel) as handle:
            try:
                with zipfile.ZipFile(handle) as archive:
                    listing = _list_archive(archive)
            except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
                raise MediaUnavailableError(media_id) from exc
        self._listings[key] = listing
        while len(self._listings) > LISTING_CACHE_SIZE:
            self._listings.popitem(last=False)
        return listing

    def archive_page(self, media_id: str, index: int) -> tuple[bytes, str]:
        """The bytes and content type of page ``index`` of an image archive."""
        listing = self.archive_listing(media_id)
        if not 0 <= index < len(listing.pages):
            raise MediaUnavailableError(media_id)
        rel, _record = self._lookup(media_id)
        with self._open(rel) as handle:
            try:
                with zipfile.ZipFile(handle) as archive:
                    infos = _image_entries(archive)
                    if index >= len(infos):
                        raise MediaUnavailableError(media_id)
                    info = infos[index]
                    if info.file_size > MAX_PAGE_BYTES:
                        raise MediaUnavailableError(media_id)
                    with archive.open(info) as entry:
                        # Read one byte past the cap: a header can understate
                        # the real size, and the cap must hold regardless.
                        data = entry.read(MAX_PAGE_BYTES + 1)
            except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
                raise MediaUnavailableError(media_id) from exc
        if len(data) > MAX_PAGE_BYTES:
            raise MediaUnavailableError(media_id)
        extension = os.path.splitext(info.filename)[1].lower()
        return data, IMAGE_TYPES.get(extension, "application/octet-stream")


# ---------------------------------------------------------------------------
def _same_location(a: str, b: str) -> bool:
    def normal(path: str) -> str:
        return os.path.normcase(os.path.realpath(path)).rstrip("\\/")

    return normal(a) == normal(b)


def is_video_entry(name: str, size: int) -> bool:
    """Whether an entry inside an archive is footage, judged by name and size."""
    lowered = name.lower()
    extension = os.path.splitext(lowered)[1]
    if extension not in VIDEO_TYPES:
        return False
    if extension == ".ts":
        return not lowered.endswith(".d.ts") and size >= MIN_TRANSPORT_STREAM_BYTES
    return True


def _describe(media_id: str, rel: str, record: dict[str, Any]) -> MediaFile:
    name = rel.replace("\\", "/").rsplit("/", 1)[-1]
    extension = os.path.splitext(name)[1].lower()
    kind = str(record.get("kind") or "other")
    raw_archive = record.get("archive")
    archive: dict[str, Any] = raw_archive if isinstance(raw_archive, dict) else {}
    images = int(archive.get("images") or 0)
    recorded = [e for e in (archive.get("video_entries") or []) if isinstance(e, dict)]
    videos_only = [
        e for e in recorded if is_video_entry(str(e.get("name") or ""), int(e.get("size") or 0))
    ]
    # Older scans counted every ".ts" entry; drop the ones that are not footage.
    videos = max(int(archive.get("videos") or 0) - (len(recorded) - len(videos_only)), 0)
    if int(archive.get("executables") or 0):
        # Software is never presented as media, whatever else the archive holds.
        kind, images, videos, videos_only = "software", 0, 0, []
    if extension in VIDEO_TYPES:
        view, content_type = "video", VIDEO_TYPES[extension]
    elif extension in DOCUMENT_TYPES:
        view, content_type = "document", DOCUMENT_TYPES[extension]
    elif extension in ARCHIVE_EXTENSIONS and images:
        view, content_type = "pages", None
    elif extension in ARCHIVE_EXTENSIONS and videos:
        view, content_type = "bundle", None
    else:
        view, content_type = "none", None
    entries = tuple(
        {
            "name": str(e.get("name") or "").replace("\\", "/").rsplit("/", 1)[-1],
            "size": int(e.get("size") or 0),
        }
        for e in videos_only
    )
    return MediaFile(
        id=media_id,
        name=name,
        extension=extension,
        kind=kind,
        size_bytes=int(record.get("size") or 0),
        content_type=content_type,
        view=view,
        archive_images=images,
        archive_videos=videos,
        archive_video_entries=entries,
        relative=rel,
    )


def _image_entries(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """Image entries in reading order: by folder, then by natural file order."""
    infos = [
        info
        for info in archive.infolist()
        if not info.is_dir()
        and os.path.splitext(info.filename)[1].lower() in IMAGE_TYPES
        and not info.filename.replace("\\", "/").rsplit("/", 1)[-1].startswith(".")
    ]
    infos.sort(key=lambda info: _natural_key(info.filename.replace("\\", "/")))
    return infos


def _list_archive(archive: zipfile.ZipFile) -> ArchiveListing:
    images = _image_entries(archive)
    pages: list[ArchivePage] = []
    chapters: list[tuple[str, int, int]] = []
    for position, info in enumerate(images):
        parts = [p for p in info.filename.replace("\\", "/").split("/") if p]
        chapter = "/".join(parts[:-1])
        pages.append(
            ArchivePage(index=position, label=parts[-1], chapter=chapter, size_bytes=info.file_size)
        )
        if not chapters or chapters[-1][0] != chapter:
            chapters.append((chapter, position, 1))
        else:
            label, first, count = chapters[-1]
            chapters[-1] = (label, first, count + 1)
    videos = tuple(
        {"name": info.filename.replace("\\", "/").rsplit("/", 1)[-1], "size": info.file_size}
        for info in archive.infolist()
        if not info.is_dir() and is_video_entry(info.filename, info.file_size)
    )
    other = sum(1 for info in archive.infolist() if not info.is_dir()) - len(images) - len(videos)
    return ArchiveListing(
        pages=tuple(pages), chapters=tuple(chapters), videos=videos, other_entries=max(other, 0)
    )
