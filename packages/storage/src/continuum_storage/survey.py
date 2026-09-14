"""Read-only survey of catalog roots: walk, fingerprint, inspect archives, hash.

The full-Vault catalog (Phase 1.5) needs four observations about every file
under every configured catalog root, and all four are reads:

* **walk** - every file, its size and mtime, and every entry deliberately
  *not* followed (system files, links leaving the root) with the reason;
* **probe** - what the bytes are (by signature) and a quick fingerprint;
* **inspect** - for ZIP/CBZ archives, the central directory: how many images,
  videos and other members, the image folders in reading order and each video
  member's size, CRC and compression - without reading or extracting a member;
* **hash** - the full SHA-256, streamed, refused if the file changed meanwhile.

Catalog roots are the Source Vault and the configured intake folders. Both
are read through :class:`SourceVaultReader`, which has no write method: this
module cannot modify, rename or delete anything it surveys (ADR-0001).
"""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from continuum_config import Settings
from continuum_core import ContinuumError, ErrorCategory, PathEscapesRootError
from continuum_imaging.formats import sniff

from continuum_storage.media import IMAGE_TYPES, _image_entries, is_video_entry
from continuum_storage.sources import normalized_entry
from continuum_storage.vault import SourceVaultReader

__all__ = [
    "ArchiveInspection",
    "ArchiveMemberInfo",
    "ArchivePageGroup",
    "CatalogRoot",
    "FileChangedError",
    "FileProbe",
    "SurveyReadError",
    "SurveySkip",
    "SurveyedFile",
    "VaultSurvey",
    "catalog_roots",
    "hash_catalog_file",
    "inspect_archive",
    "probe_file",
    "stat_file",
    "survey_root",
]

VAULT_ROOT_KEY = "source_vault"
#: Bytes read from each end of a file for its quick fingerprint.
FINGERPRINT_EDGE_BYTES = 64 * 1024
HASH_CHUNK_BYTES = 4 * 1024 * 1024
_DOCUMENT_EXTENSIONS = frozenset({".pdf", ".txt", ".md", ".xml", ".json", ".nfo", ".ass", ".srt"})


class SurveyReadError(ContinuumError):
    """A file or archive could not be read. Recorded, never fatal to a scan."""

    code = "catalog.read_failed"
    category = ErrorCategory.RETRYABLE_TRANSIENT


class FileChangedError(ContinuumError):
    """A file changed while it was being read; its observation is not trusted."""

    code = "catalog.file_changed"
    category = ErrorCategory.RETRYABLE_TRANSIENT


@dataclass(frozen=True, slots=True)
class CatalogRoot:
    """One read-only folder the catalog covers."""

    key: str
    """``source_vault`` or ``intake:<slug>``; never a path."""
    collection: str
    """Empty for the Source Vault; the configured collection name otherwise."""
    material: str
    """The material class an intake folder declares ('' for the Vault)."""
    reader: SourceVaultReader = field(repr=False)

    @property
    def is_vault(self) -> bool:
        return self.key == VAULT_ROOT_KEY

    def available(self) -> bool:
        return self.reader.exists()


def catalog_roots(settings: Settings) -> list[CatalogRoot]:
    """The Source Vault (when configured) and every configured intake folder.

    An intake pair may name a material class after the collection name:
    ``FanArt:fan_art=D:/Intake/FanArt``. Without one, intake material is plain
    reference material.
    """
    roots: list[CatalogRoot] = []
    vault = settings.source_vault_root
    if vault:
        roots.append(
            CatalogRoot(
                key=VAULT_ROOT_KEY,
                collection="",
                material="",
                reader=SourceVaultReader(vault, root_key=VAULT_ROOT_KEY),
            )
        )
    for key, (collection, material, path) in settings.intake_root_map().items():
        roots.append(
            CatalogRoot(
                key=key,
                collection=collection,
                material=material,
                reader=SourceVaultReader(path, root_key=key),
            )
        )
    return roots


# ---------------------------------------------------------------------------
# walk
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class SurveyedFile:
    relative: str
    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class SurveySkip:
    """An entry deliberately not catalogued, and why - so coverage can explain it."""

    relative: str
    reason: str


@dataclass(frozen=True, slots=True)
class VaultSurvey:
    root_key: str
    available: bool
    files: tuple[SurveyedFile, ...]
    skipped: tuple[SurveySkip, ...]
    directories: int


def survey_root(root: CatalogRoot) -> VaultSurvey:
    """Every file under a root, sorted by relative path, plus what was skipped.

    Links and junctions are never followed: one that leads outside the root is
    skipped as an escape, one inside it as a duplicate view of the same files.
    """
    base = root.reader.root
    if not root.reader.exists():
        return VaultSurvey(root.key, False, (), (), 0)
    files: list[SurveyedFile] = []
    skipped: list[SurveySkip] = []
    directories = 0
    stack: list[Path] = [base]
    while stack:
        current = stack.pop()
        directories += 1
        try:
            with os.scandir(current) as iterator:
                entries = sorted(iterator, key=lambda e: e.name)
        except OSError as exc:
            skipped.append(
                SurveySkip(
                    _relative(base, Path(current)), f"folder unreadable: {exc.strerror or exc}"
                )
            )
            continue
        for entry in entries:
            path = Path(entry.path)
            relative = _relative(base, path)
            if entry.name.lower() in SourceVaultReader.IGNORED_NAMES:
                skipped.append(
                    SurveySkip(relative, "system file written by the OS or a sync client")
                )
                continue
            try:
                linked = entry.is_symlink() or entry.is_junction()
            except OSError:
                linked = False
            if linked:
                try:
                    target = path.resolve()
                    target.relative_to(base)
                    reason = "link to another place inside the root (not followed)"
                except (OSError, ValueError):
                    reason = "link leading outside the root (never followed)"
                skipped.append(SurveySkip(relative, reason))
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    skipped.append(SurveySkip(relative, "not a regular file"))
                    continue
                info = entry.stat(follow_symlinks=False)
            except OSError as exc:
                skipped.append(SurveySkip(relative, f"unreadable: {exc.strerror or exc}"))
                continue
            if "\\" in relative or any(part in ("", ".", "..") for part in relative.split("/")):
                skipped.append(SurveySkip(relative, "name cannot be addressed safely"))
                continue
            files.append(SurveyedFile(relative, int(info.st_size), int(info.st_mtime_ns)))
    files.sort(key=lambda f: f.relative)
    skipped.sort(key=lambda s: s.relative)
    return VaultSurvey(root.key, True, tuple(files), tuple(skipped), directories)


def _relative(base: Path, path: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FileProbe:
    size: int
    mtime_ns: int
    #: "image", "video" or "other" - by signature.
    sniffed_kind: str
    sniffed_format: str
    description: str
    #: SHA-256 over the size and the first and last 64 KiB. Cheap change
    #: detection; never used as content identity.
    quick_fingerprint: str
    extension: str


def _stat(root: CatalogRoot, relative: str) -> os.stat_result:
    try:
        info = root.reader.stat(PurePath(relative))
    except (PathEscapesRootError, OSError, ValueError) as exc:
        raise SurveyReadError(
            "That file could not be found in its folder.", technical_detail=str(exc)
        ) from None
    if not stat.S_ISREG(info.st_mode):
        raise SurveyReadError("That entry is not a regular file.")
    return info


def stat_file(root: CatalogRoot, relative: str) -> tuple[int, int] | None:
    """Size and mtime of a catalogued file, or None when it is gone."""
    try:
        info = root.reader.stat(PurePath(relative))
    except (PathEscapesRootError, OSError, ValueError):
        return None
    if not stat.S_ISREG(info.st_mode):
        return None
    return int(info.st_size), int(info.st_mtime_ns)


def probe_file(root: CatalogRoot, relative: str) -> FileProbe:
    """What a file is, from its first bytes, plus a quick fingerprint."""
    try:
        with root.reader.open_read(PurePath(relative)) as handle:
            info = os.fstat(handle.fileno())
            size = int(info.st_size)
            head = handle.read(FINGERPRINT_EDGE_BYTES)
            if size > 2 * FINGERPRINT_EDGE_BYTES:
                handle.seek(size - FINGERPRINT_EDGE_BYTES)
                tail = handle.read(FINGERPRINT_EDGE_BYTES)
            else:
                tail = b""
    except (PathEscapesRootError, OSError, ValueError) as exc:
        raise SurveyReadError("That file could not be read.", technical_detail=str(exc)) from None
    digest = hashlib.sha256()
    digest.update(f"continuum-quick/1:{size}:".encode())
    digest.update(head)
    digest.update(tail)
    sniffed = sniff(head)
    return FileProbe(
        size=size,
        mtime_ns=int(info.st_mtime_ns),
        sniffed_kind=sniffed.kind,
        sniffed_format=sniffed.format,
        description=sniffed.description,
        quick_fingerprint=digest.hexdigest(),
        extension=os.path.splitext(relative)[1].lower(),
    )


# ---------------------------------------------------------------------------
# archives
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ArchivePageGroup:
    """One folder of images, as the Reader pages through it."""

    folder: str
    first_index: int
    count: int


@dataclass(frozen=True, slots=True)
class ArchiveMemberInfo:
    """One video inside an archive, from the central directory alone."""

    name: str
    position: int
    size: int
    compressed_size: int
    crc32: int
    compress_type: int
    encrypted: bool


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    entries: int
    images: int
    videos: int
    executables: int
    documents: int
    other: int
    encrypted: int
    unaddressable: int
    groups: tuple[ArchivePageGroup, ...]
    video_members: tuple[ArchiveMemberInfo, ...]
    has_comic_info: bool

    @property
    def view(self) -> str:
        """The same content-based view the Library viewer uses."""
        if self.executables:
            return "none"
        if self.images and self.videos:
            return "mixed"
        if self.images:
            return "pages"
        if self.videos:
            return "bundle"
        return "none"


def inspect_archive(root: CatalogRoot, relative: str) -> ArchiveInspection:
    """Read an archive's central directory. No member is read or extracted."""
    try:
        with (
            root.reader.open_read(PurePath(relative)) as handle,
            zipfile.ZipFile(handle) as archive,
        ):
            infos = [i for i in archive.infolist() if not i.is_dir()]
            image_infos = _image_entries(archive)
    except (PathEscapesRootError, OSError, ValueError) as exc:
        raise SurveyReadError(
            "That archive could not be read.", technical_detail=str(exc)
        ) from None
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError) as exc:
        raise SurveyReadError(
            "That archive is damaged or uses a format Continuum cannot read.",
            technical_detail=f"{type(exc).__name__}: {exc}",
        ) from None

    groups: list[ArchivePageGroup] = []
    for position, info in enumerate(image_infos):
        parts = [p for p in info.filename.replace("\\", "/").split("/") if p]
        folder = "/".join(parts[:-1])
        if groups and groups[-1].folder == folder:
            last = groups[-1]
            groups[-1] = ArchivePageGroup(last.folder, last.first_index, last.count + 1)
        else:
            groups.append(ArchivePageGroup(folder, position, 1))

    videos: list[ArchiveMemberInfo] = []
    executables = documents = other = encrypted = unaddressable = 0
    image_names = {id(i) for i in image_infos}
    has_comic_info = False
    for position, info in enumerate(infos):
        lowered = info.filename.lower()
        extension = os.path.splitext(lowered)[1]
        if info.flag_bits & 0x1:
            encrypted += 1
        if lowered.rsplit("/", 1)[-1] == "comicinfo.xml":
            has_comic_info = True
        name = normalized_entry(info.filename)
        if name is None:
            unaddressable += 1
            continue
        if id(info) in image_names:
            continue
        if is_video_entry(info.filename, info.file_size):
            videos.append(
                ArchiveMemberInfo(
                    name=name,
                    position=position,
                    size=int(info.file_size),
                    compressed_size=int(info.compress_size),
                    crc32=int(info.CRC),
                    compress_type=int(info.compress_type),
                    encrypted=bool(info.flag_bits & 0x1),
                )
            )
        elif extension in (".exe", ".msi", ".dll", ".bat", ".cmd", ".com", ".scr"):
            executables += 1
        elif extension in _DOCUMENT_EXTENSIONS:
            documents += 1
        elif extension not in IMAGE_TYPES:
            other += 1
    videos.sort(key=lambda v: v.name)
    return ArchiveInspection(
        entries=len(infos),
        images=len(image_infos),
        videos=len(videos),
        executables=executables,
        documents=documents,
        other=other,
        encrypted=encrypted,
        unaddressable=unaddressable,
        groups=tuple(groups),
        video_members=tuple(videos),
        has_comic_info=has_comic_info,
    )


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------
def hash_catalog_file(
    root: CatalogRoot,
    relative: str,
    *,
    expected_size: int,
    expected_mtime_ns: int,
    on_progress: Callable[[int], None] | None = None,
) -> str:
    """Stream a file's SHA-256, refusing if it is not the file that was observed.

    Size and mtime are compared before and after reading, so a file replaced or
    still being written never receives a hash that belongs to other bytes.
    """
    info = _stat(root, relative)
    if (int(info.st_size), int(info.st_mtime_ns)) != (expected_size, expected_mtime_ns):
        raise FileChangedError("The file changed since it was observed; rescan it first.")
    digest = hashlib.sha256()
    read = 0
    try:
        with root.reader.open_read(PurePath(relative)) as handle:
            while True:
                chunk = handle.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
                read += len(chunk)
                if on_progress is not None:
                    on_progress(read)
    except (PathEscapesRootError, OSError, ValueError) as exc:
        raise SurveyReadError("That file could not be read.", technical_detail=str(exc)) from None
    after = _stat(root, relative)
    if read != expected_size or (int(after.st_size), int(after.st_mtime_ns)) != (
        expected_size,
        expected_mtime_ns,
    ):
        raise FileChangedError("The file changed while it was being hashed.")
    return digest.hexdigest()
