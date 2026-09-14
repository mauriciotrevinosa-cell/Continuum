"""The full-Vault catalog: observe every file, interpret it honestly, keep it current.

What this service guarantees, below any API or job:

* **Everything is accounted for.** Every file under every catalog root ends in
  exactly one state - ``CATALOGUED``, ``UNSUPPORTED`` (with the reason),
  ``FAILED`` (with the error, retried by the next scan) or ``MISSING`` - and
  every entry the walk deliberately skipped is recorded on the scan.
* **Unchanged means untouched.** A file whose size and mtime match its last
  observation under the same scanner version is not reopened, and a recorded
  hash is reused while the file keeps the size and mtime it was hashed at. The
  acquisition engine's hashes are reused the same way. Nothing re-hashes a
  terabyte because the application restarted.
* **Interpretation is labelled.** Units (chapters, episodes) carry a confidence,
  the evidence behind them and flags for anything uncertain.
* **Read-only over the roots.** Every read goes through
  :mod:`continuum_storage.survey`, which cannot write. Only catalog rows change.

The caller owns the transaction: a durable job unit commits the effect together
with its completion record.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from continuum_core.catalog import (
    SCANNER_VERSION,
    Confidence,
    DetectedKind,
    EntryStatus,
    EpisodeKind,
    HashSource,
    MaterialClass,
    MemberKind,
    ScanStatus,
    UnitKind,
)
from continuum_core.hashing import is_sha256_hex
from continuum_db.models import CatalogEntry, CatalogMember, CatalogScan, CatalogUnit
from continuum_storage.survey import (
    ArchiveInspection,
    CatalogRoot,
    FileChangedError,
    FileProbe,
    SurveyedFile,
    SurveyReadError,
    VaultSurvey,
    hash_catalog_file,
    inspect_archive,
    probe_file,
    stat_file,
)
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from continuum_library.identify import (
    Placement,
    identify_chapter,
    identify_episode,
    place,
)
from continuum_library.inbox import download_name_facts
from continuum_library.validation import CatalogNotFoundError

__all__ = [
    "MAX_RECORDED_SKIPS",
    "ObserveOutcome",
    "VaultCatalog",
    "unit_key_for",
    "works_aliases",
]

#: Skipped entries listed individually on a scan; the rest are counted by reason.
MAX_RECORDED_SKIPS = 2000
_REFERENCE_IMAGE_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "GIF", "HEIF"})
_ARCHIVE_EXTENSIONS = frozenset({".zip", ".cbz"})
_TEXT_EXTENSIONS = frozenset(
    {".txt", ".md", ".nfo", ".xml", ".json", ".srt", ".ass", ".ssa", ".url"}
)
_KIND_ORDER = {
    EpisodeKind.REGULAR: 0,
    EpisodeKind.RECAP: 0,
    EpisodeKind.SPECIAL: 1,
    EpisodeKind.OVA: 2,
    EpisodeKind.MOVIE: 3,
    EpisodeKind.UNKNOWN: 4,
}


def unit_key_for(root_key: str, relative: str, address: str) -> str:
    """A unit's stable identity: where it lives, never a row id.

    ``address`` names the unit inside its file: ``file`` for the whole file,
    ``pages:<folder>`` for a group of archive pages, ``member:<entry>`` for a
    video inside an archive. Progress and references keyed by it survive
    every rescan and re-identification.
    """
    digest = hashlib.sha256(f"continuum-unit/1\x00{root_key}\x00{relative}\x00{address}".encode())
    return digest.hexdigest()[:40]


def works_aliases(works_catalog: Mapping[str, Any] | None) -> dict[str, tuple[str, ...]]:
    """Known titles per Vault series folder, from the acquisition engine's works catalog.

    Used only as evidence when a file name uses another title than its folder;
    nothing is renamed or regrouped because of it.
    """
    out: dict[str, tuple[str, ...]] = {}
    families = (works_catalog or {}).get("families") or []
    for family in families if isinstance(families, list) else []:
        if not isinstance(family, dict):
            continue
        folder = str(family.get("vault_family_folder") or "").strip()
        if not folder:
            continue
        names: list[str] = [str(family.get("family") or "")]
        for work in family.get("works") or []:
            if not isinstance(work, dict):
                continue
            names.append(str(work.get("work") or ""))
            titles = work.get("titles")
            if isinstance(titles, dict):
                names.extend(str(v) for v in titles.values() if isinstance(v, str))
            for key in ("intake_aliases", "aliases"):
                values = work.get(key)
                if isinstance(values, list):
                    names.extend(str(v) for v in values if isinstance(v, str))
        cleaned = tuple(dict.fromkeys(n.strip() for n in names if n and n.strip()))[:80]
        out[folder] = cleaned
    return out


@dataclass(frozen=True, slots=True)
class ObserveOutcome:
    relative: str
    #: new, changed, unchanged, failed or unsupported
    state: str
    entry_id: uuid.UUID | None


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class VaultCatalog:
    """Catalog operations inside one database session (the caller commits)."""

    def __init__(
        self,
        session: Session,
        roots: Sequence[CatalogRoot],
        *,
        engine_records: Mapping[str, Any] | None = None,
        aliases: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.session = session
        self.roots = {root.key: root for root in roots}
        self._engine = engine_records or {}
        self._aliases = aliases or {}

    # =====================================================================
    # roots and scans
    # =====================================================================
    def root(self, root_key: str) -> CatalogRoot:
        found = self.roots.get(root_key)
        if found is None:
            raise CatalogNotFoundError("That catalog folder is not configured.")
        return found

    def scan_for_job(self, root_key: str, job_id: uuid.UUID | None) -> CatalogScan:
        """The running scan of a job, created once - a resumed job keeps its scan."""
        if job_id is not None:
            existing = self.session.execute(
                select(CatalogScan).where(
                    CatalogScan.job_id == job_id, CatalogScan.root_key == root_key
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing
        scan = CatalogScan(
            root_key=root_key,
            job_id=job_id,
            status=ScanStatus.RUNNING,
            scanner_version=SCANNER_VERSION,
            survey={},
            counts={},
        )
        self.session.add(scan)
        self.session.flush()
        return scan

    def record_survey(self, scan: CatalogScan, survey: VaultSurvey) -> None:
        reasons: dict[str, int] = {}
        for skip in survey.skipped:
            reasons[skip.reason] = reasons.get(skip.reason, 0) + 1
        scan.survey = {
            "available": survey.available,
            "files": len(survey.files),
            "bytes": sum(f.size for f in survey.files),
            "directories": survey.directories,
            "skipped": len(survey.skipped),
            "skipped_by_reason": reasons,
            "skipped_entries": [
                {"relative": s.relative, "reason": s.reason}
                for s in survey.skipped[:MAX_RECORDED_SKIPS]
            ],
        }
        self.session.flush()

    # =====================================================================
    # observation
    # =====================================================================
    def observe(self, scan: CatalogScan, root: CatalogRoot, seen: SurveyedFile) -> ObserveOutcome:
        """Observe one surveyed file. Repeat-safe: a second run is a no-op."""
        entry = self._entry(root.key, seen.relative)
        if (
            entry is not None
            and entry.byte_size == seen.size
            and entry.mtime_ns == seen.mtime_ns
            and entry.scanner_version == SCANNER_VERSION
            and entry.status in (EntryStatus.CATALOGUED, EntryStatus.UNSUPPORTED)
        ):
            if entry.last_seen_scan_id != scan.id:
                # Seen again, nothing else: ``updated_at`` keeps meaning "the
                # observation changed", so nothing downstream rebuilds.
                self.session.execute(
                    update(CatalogEntry)
                    .where(CatalogEntry.id == entry.id)
                    .values(
                        last_seen_scan_id=scan.id,
                        last_seen_at=_now(),
                        updated_at=CatalogEntry.updated_at,
                    )
                    .execution_options(synchronize_session=False)
                )
                self._count(scan, "unchanged")
            self.session.flush()
            return ObserveOutcome(seen.relative, "unchanged", entry.id)

        state = "new" if entry is None else "changed"
        if entry is None:
            entry = CatalogEntry(
                root_key=root.key,
                relative_path=seen.relative,
                file_name=seen.relative.rsplit("/", 1)[-1],
                extension=_extension(seen.relative),
                byte_size=seen.size,
                mtime_ns=seen.mtime_ns,
                detected_kind=DetectedKind.OTHER,
                status=EntryStatus.FAILED,
                material_class=MaterialClass.UNKNOWN,
                collection=root.collection,
                scanner_version=SCANNER_VERSION,
                facts={},
            )
            self.session.add(entry)
            self.session.flush()
        already_counted = entry.last_seen_scan_id == scan.id
        entry.last_seen_scan_id = scan.id
        entry.last_seen_at = _now()
        entry.missing_since = None
        entry.collection = root.collection
        try:
            probe = probe_file(root, seen.relative)
            inspection = (
                inspect_archive(root, seen.relative) if probe.sniffed_format == "ZIP" else None
            )
        except (SurveyReadError, FileChangedError) as exc:
            entry.byte_size, entry.mtime_ns = seen.size, seen.mtime_ns
            entry.status = EntryStatus.FAILED
            entry.status_reason = exc.user_message
            entry.last_error = f"{exc.code}: {exc.technical_detail or exc.user_message}"
            entry.attempts = (entry.attempts or 0) + 1
            if not already_counted:
                self._count(scan, "failed")
            self.session.flush()
            return ObserveOutcome(seen.relative, "failed", entry.id)

        self._apply(entry, root, probe, inspection)
        if not already_counted:
            self._count(scan, state)
            if entry.status is EntryStatus.UNSUPPORTED:
                self._count(scan, "unsupported")
        self.session.flush()
        return ObserveOutcome(
            seen.relative,
            "unsupported" if entry.status is EntryStatus.UNSUPPORTED else state,
            entry.id,
        )

    def _apply(
        self,
        entry: CatalogEntry,
        root: CatalogRoot,
        probe: FileProbe,
        inspection: ArchiveInspection | None,
    ) -> None:
        relative = entry.relative_path
        entry.byte_size, entry.mtime_ns = probe.size, probe.mtime_ns
        entry.extension = probe.extension
        entry.detected_format = probe.sniffed_format
        entry.quick_fingerprint = probe.quick_fingerprint
        entry.scanner_version = SCANNER_VERSION
        entry.attempts = 0
        entry.last_error = None
        placement = place(relative, is_vault=root.is_vault, intake_material=root.material)
        entry.series_key = placement.series_key
        entry.series_title = placement.series_title
        facts: dict[str, Any] = {
            "placement_evidence": list(placement.evidence),
            "placement_flags": list(placement.flags),
        }
        if probe.extension and _mismatch(probe.extension, probe.sniffed_format):
            facts["extension_mismatch"] = (
                f"named {probe.extension}, but the bytes are {probe.description}"
            )
        engine = self._engine_record(root, relative, probe)
        if engine:
            facts.update(engine)
        if not root.is_vault:
            facts.update(download_name_facts(entry.file_name))

        kind, status, reason, material = self._classify(probe, inspection, placement)
        entry.detected_kind = kind
        entry.status = status
        entry.status_reason = reason
        entry.material_class = material
        if placement.material is MaterialClass.UNKNOWN and material not in (
            MaterialClass.UNKNOWN,
            MaterialClass.SOFTWARE,
        ):
            facts["placement_flags"].append(
                f"material read as {material.value.lower()} from the content"
            )
        entry.facts = facts
        if inspection is not None:
            entry.archive_view = inspection.view
            entry.member_count = inspection.entries
            entry.image_count = inspection.images
            entry.video_count = inspection.videos
            entry.other_count = inspection.entries - inspection.images - inspection.videos
        else:
            entry.archive_view = None
            entry.member_count = entry.image_count = entry.video_count = entry.other_count = 0

        self._settle_hash(entry, root, relative)
        self.session.flush()
        self._replace_members_and_units(entry, root, placement, inspection)

    def _classify(
        self,
        probe: FileProbe,
        inspection: ArchiveInspection | None,
        placement: Placement,
    ) -> tuple[DetectedKind, EntryStatus, str, MaterialClass]:
        declared = placement.material
        fmt = probe.sniffed_format
        if fmt == "EMPTY":
            return DetectedKind.EMPTY, EntryStatus.UNSUPPORTED, "The file is empty.", declared
        if fmt in ("EXECUTABLE", "OLE"):
            return (
                DetectedKind.SOFTWARE,
                EntryStatus.UNSUPPORTED,
                f"This is {probe.description}, not media. Continuum never opens or runs programs.",
                MaterialClass.SOFTWARE,
            )
        if fmt in ("RAR", "SEVEN_ZIP"):
            return (
                DetectedKind.ARCHIVE,
                EntryStatus.UNSUPPORTED,
                f"This is {probe.description}. Only ZIP and CBZ archives can be read; "
                "the file is left as it is.",
                declared,
            )
        if inspection is not None:
            if inspection.executables:
                return (
                    DetectedKind.ARCHIVE,
                    EntryStatus.UNSUPPORTED,
                    f"The archive holds software ({inspection.executables} program files). "
                    "Continuum never presents software as media.",
                    MaterialClass.SOFTWARE,
                )
            if not inspection.images and not inspection.videos:
                return (
                    DetectedKind.ARCHIVE,
                    EntryStatus.UNSUPPORTED,
                    f"The archive holds no images or videos ({inspection.entries} other entries).",
                    declared,
                )
            media = inspection.images + inspection.videos
            if inspection.encrypted and inspection.encrypted >= media:
                return (
                    DetectedKind.ARCHIVE,
                    EntryStatus.UNSUPPORTED,
                    "The archive's members are encrypted; it cannot be read without its password.",
                    declared,
                )
            material = declared
            if material is MaterialClass.UNKNOWN:
                material = (
                    MaterialClass.ANIME if inspection.view == "bundle" else MaterialClass.MANGA
                )
            return DetectedKind.ARCHIVE, EntryStatus.CATALOGUED, "", material
        if probe.sniffed_kind == "video":
            material = declared if declared is not MaterialClass.UNKNOWN else MaterialClass.ANIME
            return DetectedKind.VIDEO, EntryStatus.CATALOGUED, "", material
        if probe.sniffed_kind == "image":
            material = (
                declared if declared is not MaterialClass.UNKNOWN else MaterialClass.REFERENCE
            )
            return DetectedKind.IMAGE, EntryStatus.CATALOGUED, "", material
        if fmt == "PDF":
            material = declared if declared is not MaterialClass.UNKNOWN else MaterialClass.DOCUMENT
            return DetectedKind.DOCUMENT, EntryStatus.CATALOGUED, "", material
        if probe.extension in _TEXT_EXTENSIONS:
            return (
                DetectedKind.DOCUMENT,
                EntryStatus.UNSUPPORTED,
                "A text or subtitle file, not material; it is listed but not catalogued.",
                MaterialClass.DOCUMENT,
            )
        return (
            DetectedKind.OTHER,
            EntryStatus.UNSUPPORTED,
            f"Not a recognised media format ({probe.extension or 'no extension'}).",
            declared,
        )

    def _engine_record(self, root: CatalogRoot, relative: str, probe: FileProbe) -> dict[str, Any]:
        """Facts the acquisition engine recorded for this very file (same size and mtime)."""
        if not root.is_vault:
            return {}
        record = self._engine.get(relative)
        if not isinstance(record, dict):
            return {}
        if (
            int(record.get("size") or -1) != probe.size
            or int(record.get("mtime_ns") or -1) != probe.mtime_ns
        ):
            return {}
        raw_archive = record.get("archive")
        archive: dict[str, Any] = raw_archive if isinstance(raw_archive, dict) else {}
        facts: dict[str, Any] = {}
        for key, name in (
            ("series", "comic_info_series"),
            ("writer", "comic_info_writer"),
            ("penciller", "comic_info_penciller"),
            ("language", "comic_info_language"),
        ):
            value = archive.get(key)
            if isinstance(value, str) and value.strip():
                facts[name] = value.strip()[:300]
        return facts

    def _settle_hash(self, entry: CatalogEntry, root: CatalogRoot, relative: str) -> None:
        if (
            entry.content_hash
            and entry.hashed_size == entry.byte_size
            and entry.hashed_mtime_ns == entry.mtime_ns
        ):
            return
        entry.content_hash = None
        entry.hash_source = None
        entry.hashed_size = entry.hashed_mtime_ns = None
        if root.is_vault:
            record = self._engine.get(relative)
            if isinstance(record, dict):
                digest = record.get("sha256")
                if (
                    isinstance(digest, str)
                    and is_sha256_hex(digest)
                    and int(record.get("size") or -1) == entry.byte_size
                    and int(record.get("mtime_ns") or -1) == entry.mtime_ns
                ):
                    self._set_hash(entry, digest, HashSource.ENGINE_INDEX)

    @staticmethod
    def _set_hash(entry: CatalogEntry, digest: str, source: HashSource) -> None:
        entry.content_hash = digest
        entry.hash_source = source
        entry.hashed_size = entry.byte_size
        entry.hashed_mtime_ns = entry.mtime_ns

    # -- members and units ----------------------------------------------------
    def _replace_members_and_units(
        self,
        entry: CatalogEntry,
        root: CatalogRoot,
        placement: Placement,
        inspection: ArchiveInspection | None,
    ) -> None:
        previous_cache = {
            (m.name, m.crc32, m.byte_size): (m.cached_sha256, m.cached_at, m.last_used_at)
            for m in self.session.execute(
                select(CatalogMember).where(
                    CatalogMember.entry_id == entry.id, CatalogMember.cached_sha256.is_not(None)
                )
            ).scalars()
        }
        self.session.execute(delete(CatalogUnit).where(CatalogUnit.entry_id == entry.id))
        self.session.execute(delete(CatalogMember).where(CatalogMember.entry_id == entry.id))
        self.session.flush()
        if entry.status is not EntryStatus.CATALOGUED:
            return

        aliases = self._aliases.get(placement.series_title or "", ())
        comic_series = entry.facts.get("comic_info_series")
        if isinstance(comic_series, str) and comic_series not in aliases:
            aliases = (*aliases, comic_series)
        units: list[CatalogUnit] = []
        base = {
            "entry_id": entry.id,
            "material_class": entry.material_class,
            "collection": entry.collection,
            "series_key": entry.series_key,
            "series_title": entry.series_title,
        }

        if inspection is not None:
            for position, group in enumerate(inspection.groups):
                member = CatalogMember(
                    entry_id=entry.id,
                    kind=MemberKind.PAGE_GROUP,
                    name=group.folder,
                    position=position,
                    first_page_index=group.first_index,
                    page_count=group.count,
                )
                self.session.add(member)
                self.session.flush()
                chapter = identify_chapter(group.folder)
                kind = (
                    UnitKind.MANGA_CHAPTER if chapter.number is not None else UnitKind.ARCHIVE_PAGES
                )
                label = chapter.label if group.folder else entry.file_name.rsplit(".", 1)[0]
                units.append(
                    CatalogUnit(
                        **base,
                        unit_key=unit_key_for(
                            root.key, entry.relative_path, f"pages:{group.folder}"
                        ),
                        member_id=member.id,
                        kind=kind,
                        chapter_number=chapter.number,
                        volume=chapter.volume,
                        label=label,
                        sort_key=_chapter_sort(entry, chapter.number, group.first_index),
                        first_page_index=group.first_index,
                        page_count=group.count,
                        confidence=chapter.confidence,
                        evidence=list(chapter.evidence),
                        flags=list(chapter.flags) + list(placement.flags),
                        search_text=_search_text(
                            entry.series_title, *aliases[:6], label, entry.file_name, group.folder
                        ),
                    )
                )
            archive_stem = entry.file_name.rsplit(".", 1)[0]
            for position, video in enumerate(inspection.video_members):
                cached = previous_cache.get((video.name, video.crc32, video.size))
                member = CatalogMember(
                    entry_id=entry.id,
                    kind=MemberKind.VIDEO,
                    name=video.name,
                    position=position,
                    byte_size=video.size,
                    compressed_size=video.compressed_size,
                    crc32=video.crc32,
                    compress_type=video.compress_type,
                    encrypted=video.encrypted,
                    cached_sha256=cached[0] if cached else None,
                    cached_at=cached[1] if cached else None,
                    last_used_at=cached[2] if cached else None,
                )
                self.session.add(member)
                self.session.flush()
                folders = (*placement.subfolders, archive_stem, *video.name.split("/")[:-1])
                units.append(
                    self._video_unit(
                        base,
                        entry,
                        unit_key_for(root.key, entry.relative_path, f"member:{video.name}"),
                        video.name,
                        folders,
                        aliases,
                        member_id=member.id,
                    )
                )
        elif entry.detected_kind is DetectedKind.VIDEO:
            units.append(
                self._video_unit(
                    base,
                    entry,
                    unit_key_for(root.key, entry.relative_path, "file"),
                    entry.file_name,
                    placement.subfolders,
                    aliases,
                )
            )
        elif entry.detected_kind in (DetectedKind.IMAGE, DetectedKind.DOCUMENT):
            flags = list(placement.flags)
            if (
                entry.detected_kind is DetectedKind.IMAGE
                and entry.detected_format not in _REFERENCE_IMAGE_FORMATS
            ):
                flags.append(f"{entry.detected_format} images cannot be used as references yet")
            if "extension_mismatch" in entry.facts:
                flags.append(str(entry.facts["extension_mismatch"]))
            creator = entry.facts.get("creator_handle")
            units.append(
                CatalogUnit(
                    **base,
                    unit_key=unit_key_for(root.key, entry.relative_path, "file"),
                    kind=UnitKind.IMAGE
                    if entry.detected_kind is DetectedKind.IMAGE
                    else UnitKind.DOCUMENT,
                    label=entry.file_name,
                    sort_key=f"{entry.material_class.value}|{entry.relative_path.lower()}"[:400],
                    confidence=Confidence.HIGH if not flags else Confidence.MEDIUM,
                    evidence=list(placement.evidence),
                    flags=flags,
                    search_text=_search_text(
                        entry.series_title, entry.collection, entry.file_name, creator
                    ),
                )
            )
        for unit in units:
            self.session.add(unit)
        self.session.flush()

    def _video_unit(
        self,
        base: dict[str, Any],
        entry: CatalogEntry,
        unit_key: str,
        name: str,
        folders: Iterable[str],
        aliases: tuple[str, ...],
        *,
        member_id: uuid.UUID | None = None,
    ) -> CatalogUnit:
        identity = identify_episode(
            name, series_title=entry.series_title, aliases=aliases, folders=tuple(folders)
        )
        is_episode = entry.material_class is MaterialClass.ANIME
        flags = list(identity.flags)
        if "extension_mismatch" in entry.facts and member_id is None:
            flags.append(str(entry.facts["extension_mismatch"]))
        creator = entry.facts.get("creator_handle")
        return CatalogUnit(
            **base,
            unit_key=unit_key,
            member_id=member_id,
            kind=UnitKind.EPISODE if is_episode else UnitKind.VIDEO,
            program_title=identity.program_title,
            season=identity.season,
            episode=identity.episode,
            episode_kind=identity.kind if is_episode else None,
            label=identity.label if is_episode else name.rsplit("/", 1)[-1],
            sort_key=_episode_sort(entry, identity.season, identity.kind, identity.episode, name),
            confidence=identity.confidence if is_episode else Confidence.HIGH,
            evidence=list(identity.evidence),
            flags=flags,
            search_text=_search_text(
                entry.series_title,
                *aliases[:6],
                identity.program_title,
                identity.label,
                name,
                entry.file_name,
                entry.collection,
                creator,
            ),
        )

    # =====================================================================
    # completion
    # =====================================================================
    def finish_scan(self, scan: CatalogScan) -> dict[str, Any]:
        """Mark what vanished, name exact duplicates, and close the scan. Repeat-safe."""
        if scan.status is ScanStatus.COMPLETED:
            return dict(scan.counts)
        counts = dict(scan.counts)
        available = bool((scan.survey or {}).get("available"))
        if available:
            missing = self.session.execute(  # type: ignore[attr-defined]
                update(CatalogEntry)
                .where(
                    CatalogEntry.root_key == scan.root_key,
                    or_(
                        CatalogEntry.last_seen_scan_id.is_(None),
                        CatalogEntry.last_seen_scan_id != scan.id,
                    ),
                    CatalogEntry.status != EntryStatus.MISSING,
                )
                .values(status=EntryStatus.MISSING, missing_since=_now())
                .execution_options(synchronize_session=False)
            ).rowcount
            counts["missing"] = int(missing or 0)
        else:
            counts["root_unavailable"] = True
        self.mark_duplicates()
        by_status: dict[Any, int] = {
            row[0]: int(row[1])
            for row in self.session.execute(
                select(CatalogEntry.status, func.count())
                .where(CatalogEntry.root_key == scan.root_key)
                .group_by(CatalogEntry.status)
            ).all()
        }
        counts["by_status"] = {
            str(k.value if hasattr(k, "value") else k): int(v) for k, v in by_status.items()
        }
        scan.counts = counts
        scan.status = ScanStatus.COMPLETED
        scan.finished_at = _now()
        self.session.flush()
        return counts

    def mark_duplicates(self) -> int:
        """Point every exact byte duplicate at its first copy. Nothing is deleted."""
        # The first copy: Source Vault before intake folders, then the oldest
        # file, then the shortest name ("part-01" before "part-01 (1)").
        rows = self.session.execute(
            select(CatalogEntry.id, CatalogEntry.content_hash)
            .where(
                CatalogEntry.content_hash.is_not(None),
                CatalogEntry.status == EntryStatus.CATALOGUED,
            )
            .order_by(
                CatalogEntry.content_hash,
                CatalogEntry.root_key.desc(),
                CatalogEntry.mtime_ns,
                func.length(CatalogEntry.relative_path),
                CatalogEntry.relative_path,
            )
        ).all()
        first: dict[str, uuid.UUID] = {}
        wanted: dict[uuid.UUID, uuid.UUID | None] = {}
        for entry_id, digest in rows:
            if digest in first:
                wanted[entry_id] = first[digest]
            else:
                first[digest] = entry_id
                wanted[entry_id] = None
        changed = 0
        current: dict[uuid.UUID, uuid.UUID | None] = {
            row[0]: row[1]
            for row in self.session.execute(
                select(CatalogEntry.id, CatalogEntry.duplicate_of_id).where(
                    CatalogEntry.id.in_(list(wanted)) if wanted else CatalogEntry.id.is_(None)
                )
            ).all()
        }
        for entry_id, target in wanted.items():
            if current.get(entry_id) != target:
                self.session.execute(
                    update(CatalogEntry)
                    .where(CatalogEntry.id == entry_id)
                    .values(duplicate_of_id=target)
                    .execution_options(synchronize_session=False)
                )
                changed += 1
        # An entry that is no longer catalogued or hashed stops pointing anywhere.
        self.session.execute(
            update(CatalogEntry)
            .where(
                CatalogEntry.duplicate_of_id.is_not(None),
                or_(
                    CatalogEntry.content_hash.is_(None),
                    CatalogEntry.status != EntryStatus.CATALOGUED,
                ),
            )
            .values(duplicate_of_id=None)
            .execution_options(synchronize_session=False)
        )
        self.session.flush()
        return changed

    # =====================================================================
    # hashing
    # =====================================================================
    def entries_needing_hash(self, root_key: str) -> list[tuple[uuid.UUID, int, int]]:
        """Catalogued entries without a hash valid for their current size and mtime."""
        rows = self.session.execute(
            select(CatalogEntry.id, CatalogEntry.byte_size, CatalogEntry.mtime_ns)
            .where(
                CatalogEntry.root_key == root_key,
                CatalogEntry.status == EntryStatus.CATALOGUED,
                or_(
                    CatalogEntry.content_hash.is_(None),
                    CatalogEntry.hashed_size != CatalogEntry.byte_size,
                    CatalogEntry.hashed_mtime_ns != CatalogEntry.mtime_ns,
                ),
            )
            .order_by(CatalogEntry.byte_size, CatalogEntry.relative_path)
        ).all()
        return [(row[0], int(row[1]), int(row[2])) for row in rows]

    def hash_entry(self, entry_id: uuid.UUID) -> str | None:
        """Hash one entry if it still needs it. Returns the hash, or None if skipped."""
        entry = self.session.get(CatalogEntry, entry_id)
        if entry is None or entry.status is not EntryStatus.CATALOGUED:
            return None
        if (
            entry.content_hash
            and entry.hashed_size == entry.byte_size
            and entry.hashed_mtime_ns == entry.mtime_ns
        ):
            return entry.content_hash
        root = self.root(entry.root_key)
        current = stat_file(root, entry.relative_path)
        if current is None:
            entry.status = EntryStatus.MISSING
            entry.missing_since = _now()
            self.session.flush()
            return None
        if current != (entry.byte_size, entry.mtime_ns):
            # Changed since observation: the next scan re-observes it first.
            entry.scanner_version = 0
            self.session.flush()
            return None
        try:
            digest = hash_catalog_file(
                root,
                entry.relative_path,
                expected_size=entry.byte_size,
                expected_mtime_ns=entry.mtime_ns,
            )
        except FileChangedError:
            entry.scanner_version = 0
            self.session.flush()
            return None
        except SurveyReadError as exc:
            entry.last_error = f"{exc.code}: {exc.technical_detail or exc.user_message}"
            entry.attempts = (entry.attempts or 0) + 1
            self.session.flush()
            return None
        self._set_hash(entry, digest, HashSource.COMPUTED)
        self.session.flush()
        return digest

    # =====================================================================
    # helpers
    # =====================================================================
    def _entry(self, root_key: str, relative: str) -> CatalogEntry | None:
        return self.session.execute(
            select(CatalogEntry).where(
                and_(CatalogEntry.root_key == root_key, CatalogEntry.relative_path == relative)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _count(scan: CatalogScan, key: str) -> None:
        counts = dict(scan.counts or {})
        counts[key] = int(counts.get(key, 0)) + 1
        scan.counts = counts


# ---------------------------------------------------------------------------
def _extension(relative: str) -> str:
    name = relative.rsplit("/", 1)[-1]
    return ("." + name.rsplit(".", 1)[-1].lower())[:24] if "." in name else ""


_FORMAT_EXTENSIONS: dict[str, frozenset[str]] = {
    "JPEG": frozenset({".jpg", ".jpeg", ".jfif"}),
    "PNG": frozenset({".png"}),
    "WEBP": frozenset({".webp"}),
    "GIF": frozenset({".gif"}),
    "HEIF": frozenset({".heic", ".heif"}),
    "AVIF": frozenset({".avif"}),
    "MP4": frozenset({".mp4", ".m4v"}),
    "QUICKTIME": frozenset({".mov"}),
    "MATROSKA": frozenset({".mkv", ".webm"}),
    "ZIP": frozenset({".zip", ".cbz"}),
    "PDF": frozenset({".pdf"}),
}


def _mismatch(extension: str, fmt: str) -> bool:
    expected = _FORMAT_EXTENSIONS.get(fmt)
    return expected is not None and extension not in expected


def _search_text(*parts: str | None) -> str:
    words = " ".join(p for p in parts if p)
    return " ".join(words.lower().replace("_", " ").split())[:4000]


def _chapter_sort(entry: CatalogEntry, number: Decimal | None, first_index: int) -> str:
    numeric = f"{float(number):012.3f}" if number is not None else "999999999.999"
    return (
        f"{entry.material_class.value}|{numeric}|{entry.relative_path.lower()}|{first_index:06d}"[
            :400
        ]
    )


def _episode_sort(
    entry: CatalogEntry,
    season: int | None,
    kind: EpisodeKind,
    episode: int | None,
    name: str,
) -> str:
    season_part = f"{season:04d}" if season is not None else "9999"
    episode_part = f"{episode:06d}" if episode is not None else "999999"
    order = _KIND_ORDER.get(kind, 4)
    material = entry.material_class.value
    return f"{material}|{season_part}|{order}|{episode_part}|{name.lower()}"[:400]
