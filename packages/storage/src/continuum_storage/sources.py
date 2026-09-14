"""Manga source access: held media as content-addressed reference units (Phase 1).

The Library viewer addresses held files by opaque media ids and archive pages
by position. A *reference* needs more than that: a name for the exact bytes
that survives rescans, restores and folder moves (ADR-0005). This module
bridges the two, read-only:

* :meth:`SourceAccess.select` turns a media id plus a unit choice (archive
  page index, PDF page, or the whole image) into a :class:`HeldUnit`: its
  content hash, its content-derived locator (archive **entry name**, not the
  index), and the display index it was chosen at.
* :meth:`SourceAccess.read_unit` reads a unit's bytes back from its recorded
  location - refusing if the file has changed since it was catalogued.

Nothing is copied out of the Vault, nothing is extracted to disk, and nothing
here writes anywhere. Hashing streams the file through the hardened reader;
the acquisition engine's recorded SHA-256 is reused when the file's size and
mtime still match what the engine saw.
"""

from __future__ import annotations

import os
import zipfile
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePath

from continuum_core import (
    CHUNK_BYTES,
    ContinuumError,
    ErrorCategory,
    PathEscapesRootError,
    SourceLocator,
    content_hash_stream,
    is_sha256_hex,
)
from continuum_core.locators import LocatorMedium
from continuum_core.references import AssetMedium

from continuum_storage.media import (
    ARCHIVE_EXTENSIONS,
    DOCUMENT_TYPES,
    IMAGE_TYPES,
    MAX_PAGE_BYTES,
    MediaLibrary,
    MediaUnavailableError,
    _image_entries,
)
from continuum_storage.vault import SourceVaultReader

__all__ = [
    "MAX_STANDALONE_IMAGE_BYTES",
    "HeldUnit",
    "SourceAccess",
    "SourceChangedError",
    "SourceUnavailableError",
    "UnitBytes",
    "normalized_entry",
]

#: The largest standalone image read into memory for a reference.
MAX_STANDALONE_IMAGE_BYTES = 64 * 1024 * 1024
_HASH_CACHE_SIZE = 4096


class SourceUnavailableError(ContinuumError):
    """The requested held unit does not exist or cannot be referenced."""

    code = "source.unavailable"
    category = ErrorCategory.PERMANENT_INPUT


class SourceChangedError(ContinuumError):
    """The file at a recorded location no longer holds the catalogued bytes."""

    code = "source.changed"
    category = ErrorCategory.PERMANENT_INPUT


@dataclass(frozen=True, slots=True)
class HeldUnit:
    """One referenceable unit of held media, described by its content."""

    media_id: str
    name: str
    medium: AssetMedium
    locator: SourceLocator
    unit_index: int | None
    content_hash: str
    byte_size: int
    mtime_ns: int
    #: Vault-relative, for the location record only. Never sent to a client.
    relative: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class UnitBytes:
    data: bytes
    mime: str


def normalized_entry(name: str) -> str | None:
    """An archive entry name in locator form, or None if it is not addressable.

    Separators become ``/`` and empty segments collapse; an entry with a ``.``
    or ``..`` segment (a hostile or malformed archive) is not addressable.
    """
    parts = [p for p in name.replace("\\", "/").split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        return None
    return "/".join(parts)


class SourceAccess:
    """Read-only reference access over held media."""

    def __init__(self, media: MediaLibrary, vault_root: str) -> None:
        self._media = media
        self._reader = SourceVaultReader(vault_root) if vault_root else None
        self._hashes: OrderedDict[tuple[str, int, int], str] = OrderedDict()

    # -- selection ------------------------------------------------------------
    def select(
        self,
        media_id: str,
        *,
        page_index: int | None = None,
        pdf_page: int | None = None,
        known_hash: Callable[[str, int, int], str | None] | None = None,
    ) -> HeldUnit:
        """Resolve a media id and unit choice to a content-addressed unit."""
        try:
            described = self._media.describe(media_id)
        except MediaUnavailableError:
            raise SourceUnavailableError("That media is not available.") from None
        rel = described.relative
        size, mtime = self._fingerprint(rel)
        cached = known_hash(rel, size, mtime) if known_hash is not None else None
        digest = cached if cached and is_sha256_hex(cached) else self._hash(rel, size, mtime)
        extension = described.extension

        if extension in ARCHIVE_EXTENSIONS and described.view in ("pages", "mixed"):
            if page_index is None or pdf_page is not None:
                raise SourceUnavailableError("Choose a page of the archive.")
            listing = self._media.archive_listing(media_id)
            if not 0 <= page_index < len(listing.pages):
                raise SourceUnavailableError("That page does not exist in the archive.")
            entry = self._entry_at(rel, page_index)
            return HeldUnit(
                media_id=media_id,
                name=described.name,
                medium=AssetMedium.ARCHIVE,
                locator=SourceLocator.archive_entry(digest, entry),
                unit_index=page_index,
                content_hash=digest,
                byte_size=size,
                mtime_ns=mtime,
                relative=rel,
            )
        if extension in IMAGE_TYPES:
            if page_index not in (None, 0) or pdf_page is not None:
                raise SourceUnavailableError("An image has a single unit.")
            return HeldUnit(
                media_id=media_id,
                name=described.name,
                medium=AssetMedium.IMAGE,
                locator=SourceLocator.asset(LocatorMedium.IMAGE, digest),
                unit_index=None,
                content_hash=digest,
                byte_size=size,
                mtime_ns=mtime,
                relative=rel,
            )
        if extension in DOCUMENT_TYPES:
            if pdf_page is None or pdf_page < 1 or page_index is not None:
                raise SourceUnavailableError("Choose a page of the PDF (numbered from 1).")
            return HeldUnit(
                media_id=media_id,
                name=described.name,
                medium=AssetMedium.PDF,
                locator=SourceLocator.pdf_page(digest, pdf_page),
                unit_index=pdf_page - 1,
                content_hash=digest,
                byte_size=size,
                mtime_ns=mtime,
                relative=rel,
            )
        raise SourceUnavailableError(
            "This kind of media cannot be used as a reference yet.",
            technical_detail=f"view={described.view} extension={extension}",
        )

    def video_instant(
        self,
        media_id: str,
        time_ms: int,
        *,
        known_hash: Callable[[str, int, int], str | None] | None = None,
    ) -> HeldUnit:
        """A held video and an instant in it - the provenance of a captured frame.

        The frame itself is captured by the viewer and arrives as an image; this
        records *which bytes* it came from, so the reference leads back to the
        exact episode and moment.
        """
        try:
            described = self._media.describe(media_id)
        except MediaUnavailableError:
            raise SourceUnavailableError("That media is not available.") from None
        if described.view != "video":
            raise SourceUnavailableError("Frames can only be captured from a video.")
        if time_ms < 0:
            raise SourceUnavailableError("A capture instant cannot be negative.")
        rel = described.relative
        size, mtime = self._fingerprint(rel)
        cached = known_hash(rel, size, mtime) if known_hash is not None else None
        digest = cached if cached and is_sha256_hex(cached) else self._hash(rel, size, mtime)
        return HeldUnit(
            media_id=media_id,
            name=described.name,
            medium=AssetMedium.VIDEO,
            locator=SourceLocator(medium=LocatorMedium.VIDEO, sha256=digest, time_ms=time_ms),
            unit_index=None,
            content_hash=digest,
            byte_size=size,
            mtime_ns=mtime,
            relative=rel,
        )

    # -- reading --------------------------------------------------------------
    def read_unit(
        self, relative: str, *, byte_size: int, mtime_ns: int, locator: SourceLocator
    ) -> UnitBytes:
        """The bytes of one unit at a recorded location, verified against its hash."""
        size, mtime = self._fingerprint(relative)
        if (size, mtime) != (byte_size, mtime_ns) and self._hash(
            relative, size, mtime
        ) != locator.sha256:
            raise SourceChangedError(
                "The source file has changed since this reference was made.",
                technical_detail=f"expected sha256 {locator.sha256}",
                remediation="Rescan the Library, then re-select the reference.",
            )
        if locator.medium is LocatorMedium.ZIP:
            return self._read_entry(relative, str(locator.entry))
        if locator.medium is LocatorMedium.IMAGE:
            extension = os.path.splitext(relative)[1].lower()
            with self._open(relative) as handle:
                data = handle.read(MAX_STANDALONE_IMAGE_BYTES + 1)
            if len(data) > MAX_STANDALONE_IMAGE_BYTES:
                raise SourceUnavailableError("The image is too large to use as a reference.")
            return UnitBytes(data, IMAGE_TYPES.get(extension, "application/octet-stream"))
        raise SourceUnavailableError(
            "This unit has no image bytes Continuum can read yet.",
            technical_detail=f"medium={locator.medium}",
        )

    def media_id_for(self, relative: str) -> str | None:
        """The viewer id of a recorded location, if the Library still holds it there."""
        described = self._media.describe_relative(relative)
        return described.id if described is not None else None

    def page_index_of(self, media_id: str, relative: str, entry: str) -> int | None:
        """Where an entry sits in the archive's current reading order."""
        try:
            with self._open(relative) as handle, zipfile.ZipFile(handle) as archive:
                for position, info in enumerate(_image_entries(archive)):
                    if normalized_entry(info.filename) == entry:
                        return position
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, SourceUnavailableError):
            return None
        return None

    # -- internals ------------------------------------------------------------
    def _require_reader(self) -> SourceVaultReader:
        if self._reader is None or not self._reader.exists():
            raise SourceUnavailableError("The Source Vault is not reachable on this machine.")
        return self._reader

    def _fingerprint(self, relative: str) -> tuple[int, int]:
        try:
            info = self._require_reader().stat(PurePath(relative))
        except (PathEscapesRootError, OSError, ValueError):
            raise SourceUnavailableError("That source file is not available.") from None
        return int(info.st_size), int(info.st_mtime_ns)

    def _open(self, relative: str):  # type: ignore[no-untyped-def]
        try:
            return self._require_reader().open_read(PurePath(relative))
        except (PathEscapesRootError, OSError):
            raise SourceUnavailableError("That source file is not available.") from None

    def _hash(self, relative: str, size: int, mtime: int) -> str:
        key = (relative, size, mtime)
        cached = self._hashes.get(key)
        if cached is not None:
            self._hashes.move_to_end(key)
            return cached
        record = self._media._index_files().get(relative)
        recorded = record if isinstance(record, dict) else {}
        engine_hash = recorded.get("sha256")
        if (
            isinstance(engine_hash, str)
            and is_sha256_hex(engine_hash)
            and int(recorded.get("size") or -1) == size
            and int(recorded.get("mtime_ns") or -1) == mtime
        ):
            digest = engine_hash
        else:
            with self._open(relative) as handle:
                digest = content_hash_stream(iter(lambda: handle.read(CHUNK_BYTES), b""))
        self._hashes[key] = digest
        while len(self._hashes) > _HASH_CACHE_SIZE:
            self._hashes.popitem(last=False)
        return digest

    def _entry_at(self, relative: str, index: int) -> str:
        with self._open(relative) as handle:
            try:
                with zipfile.ZipFile(handle) as archive:
                    infos = _image_entries(archive)
            except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
                raise SourceUnavailableError("The archive could not be read.") from exc
        if not 0 <= index < len(infos):
            raise SourceUnavailableError("That page does not exist in the archive.")
        entry = normalized_entry(infos[index].filename)
        if entry is None:
            raise SourceUnavailableError("That archive entry cannot be addressed safely.")
        return entry

    def _read_entry(self, relative: str, entry: str) -> UnitBytes:
        with self._open(relative) as handle:
            try:
                with zipfile.ZipFile(handle) as archive:
                    matches = [
                        info
                        for info in archive.infolist()
                        if not info.is_dir() and normalized_entry(info.filename) == entry
                    ]
                    if len(matches) != 1:
                        raise SourceUnavailableError("That page is not in the archive.")
                    info = matches[0]
                    extension = os.path.splitext(entry)[1].lower()
                    if extension not in IMAGE_TYPES or info.file_size > MAX_PAGE_BYTES:
                        raise SourceUnavailableError("That archive entry is not a usable page.")
                    with archive.open(info) as stream:
                        data = stream.read(MAX_PAGE_BYTES + 1)
            except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError) as exc:
                raise SourceUnavailableError("The archive could not be read.") from exc
        if len(data) > MAX_PAGE_BYTES:
            raise SourceUnavailableError("That page is too large.")
        return UnitBytes(data, IMAGE_TYPES.get(extension, "application/octet-stream"))
