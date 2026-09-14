"""Production reference manifests: what a generation will be given, and where it came from.

A manifest is the deterministic answer to "which inputs does this production
step use?" - resolved from the real Vault and the project, never from a
hard-coded episode or series:

* **characters** and the references a person marked preferred for them;
* **references** chosen by id, optionally with every reference the project
  marked canonical or preferred for its current look;
* **canonical source pages** - a chapter unit and a page number, resolved to
  the archive entry's content locator (``zip:sha256:...#entry=...``);
* **anime moments** - an episode unit and an instant, resolved to a video
  locator or, for a video inside an archive, ``zip:...#entry=...&t=...``;
* **project documents** with their lifecycle, maturity and content hash;
* **music references**, a **chapter package** version and **generation settings**.

The same request always resolves to the same canonical manifest and the same
SHA-256, and is stored once per project. Rights and training eligibility are
carried with every reference, and anything uncertain (unknown rights, material
not approved for training, a low-confidence identification) is listed as a
warning rather than hidden. Resolution only reads: source bytes are hashed
through the read-only storage layer, and nothing is generated here.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from continuum_core import canonical_json_hash, content_hash_bytes
from continuum_core.catalog import Confidence, EntryStatus, TrainingEligibility, UnitKind
from continuum_core.references import ProjectStanding
from continuum_db.models import (
    CatalogEntry,
    CatalogMember,
    CatalogUnit,
    ChapterPackage,
    CharacterProfile,
    MusicReference,
    ProjectReferenceStanding,
    ReferenceCharacter,
    ReferenceItem,
    ReferenceManifest,
)
from continuum_library import CatalogInputError, CatalogNotFoundError, ReferenceCatalog, region_of
from continuum_library.validation import clean_text, require_project_key
from continuum_storage import ProjectLibrary, SourceUnavailableError, media_id_for
from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = [
    "MANIFEST_SCHEMA",
    "ManifestRequest",
    "ReferenceManifests",
    "SourceMoment",
    "SourcePage",
    "manifest_view",
]

MANIFEST_SCHEMA = "continuum.reference-manifest/1"
MAX_ITEMS = 500


@dataclass(frozen=True, slots=True)
class SourcePage:
    unit_id: uuid.UUID
    #: 1-based page within the chapter (or page group).
    page: int
    note: str = ""


@dataclass(frozen=True, slots=True)
class SourceMoment:
    unit_id: uuid.UUID
    time_ms: int
    note: str = ""


@dataclass(frozen=True, slots=True)
class ManifestRequest:
    project_key: str
    label: str = ""
    purpose: str = ""
    character_ids: tuple[uuid.UUID, ...] = ()
    reference_ids: tuple[uuid.UUID, ...] = ()
    include_project_references: bool = False
    source_pages: tuple[SourcePage, ...] = ()
    source_moments: tuple[SourceMoment, ...] = ()
    document_ids: tuple[str, ...] = ()
    music_ids: tuple[uuid.UUID, ...] = ()
    chapter_package: tuple[str, int] | None = None
    generation_settings: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_key": self.project_key,
            "label": self.label,
            "purpose": self.purpose,
            "character_ids": sorted(str(i) for i in self.character_ids),
            "reference_ids": sorted(str(i) for i in self.reference_ids),
            "include_project_references": self.include_project_references,
            "source_pages": sorted(
                (
                    {"unit_id": str(p.unit_id), "page": p.page, "note": p.note}
                    for p in self.source_pages
                ),
                key=lambda d: (d["unit_id"], d["page"]),
            ),
            "source_moments": sorted(
                (
                    {"unit_id": str(m.unit_id), "time_ms": m.time_ms, "note": m.note}
                    for m in self.source_moments
                ),
                key=lambda d: (d["unit_id"], d["time_ms"]),
            ),
            "document_ids": sorted(self.document_ids),
            "music_ids": sorted(str(i) for i in self.music_ids),
            "chapter_package": list(self.chapter_package) if self.chapter_package else None,
            "generation_settings": self.generation_settings,
        }


class ReferenceManifests:
    """Resolve and store manifests inside one session (the caller commits)."""

    def __init__(
        self,
        session: Session,
        catalog: ReferenceCatalog,
        *,
        projects: ProjectLibrary | None = None,
    ) -> None:
        self.session = session
        self.catalog = catalog
        self.projects = projects

    # -- building -------------------------------------------------------------
    def build(self, request: ManifestRequest) -> ReferenceManifest:
        require_project_key(request.project_key)
        if self.projects is not None and self.projects.project(request.project_key) is None:
            raise CatalogNotFoundError("That project is not discovered on this machine.")
        total = (
            len(request.character_ids)
            + len(request.reference_ids)
            + len(request.source_pages)
            + len(request.source_moments)
            + len(request.document_ids)
            + len(request.music_ids)
        )
        if total > MAX_ITEMS:
            raise CatalogInputError(f"A manifest holds at most {MAX_ITEMS} inputs.")
        manifest = self.resolve(request)
        digest = canonical_json_hash(manifest)
        existing = self.session.execute(
            select(ReferenceManifest).where(
                ReferenceManifest.project_key == request.project_key,
                ReferenceManifest.manifest_hash == digest,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = ReferenceManifest(
            project_key=request.project_key,
            label=clean_text(request.label, 200, field="Label"),
            request=request.as_dict(),
            manifest=manifest,
            manifest_hash=digest,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def resolve(self, request: ManifestRequest) -> dict[str, Any]:
        warnings: list[str] = []
        references: dict[str, dict[str, Any]] = {}

        characters = []
        for character_id in sorted(set(request.character_ids), key=str):
            character = self.session.get(CharacterProfile, character_id)
            if character is None or character.removed_at is not None:
                raise CatalogNotFoundError("A character in the request does not exist.")
            preferred = self.session.execute(
                select(ReferenceCharacter)
                .where(
                    ReferenceCharacter.character_id == character_id,
                    ReferenceCharacter.preferred.is_(True),
                )
                .order_by(ReferenceCharacter.reference_id, ReferenceCharacter.aspect)
            ).scalars()
            links = []
            for link in preferred:
                item = self.session.get(ReferenceItem, link.reference_id)
                if item is None or item.removed_at is not None:
                    continue
                references.setdefault(
                    str(item.id), self._reference(item, request.project_key, warnings)
                )
                references[str(item.id)]["roles"].append(
                    f"character:{character_id}:{link.aspect.value}"
                )
                links.append({"reference_id": str(item.id), "aspect": link.aspect.value})
            characters.append(
                {
                    "id": str(character.id),
                    "display_name": character.display_name,
                    "subject_kind": character.subject_kind.value,
                    "source_label": character.source_label,
                    "preferred_references": links,
                }
            )

        for reference_id in sorted(set(request.reference_ids), key=str):
            item = self.session.get(ReferenceItem, reference_id)
            if item is None or item.removed_at is not None:
                raise CatalogNotFoundError("A reference in the request does not exist.")
            references.setdefault(
                str(item.id), self._reference(item, request.project_key, warnings)
            )
            references[str(item.id)]["roles"].append("selected")

        if request.include_project_references:
            standings = self.session.execute(
                select(ProjectReferenceStanding)
                .where(
                    ProjectReferenceStanding.project_key == request.project_key,
                    ProjectReferenceStanding.standing.in_(
                        [
                            ProjectStanding.CANONICAL_FOR_PROJECT,
                            ProjectStanding.PREFERRED_FOR_CURRENT_LOOK,
                        ]
                    ),
                )
                .order_by(ProjectReferenceStanding.reference_id)
            ).scalars()
            for standing in standings:
                item = self.session.get(ReferenceItem, standing.reference_id)
                if item is None or item.removed_at is not None:
                    continue
                references.setdefault(
                    str(item.id), self._reference(item, request.project_key, warnings)
                )
                references[str(item.id)]["roles"].append(f"project:{standing.standing.value}")

        sources = [self._page(page, warnings) for page in request.source_pages]
        sources += [self._moment(moment, warnings) for moment in request.source_moments]
        sources.sort(key=lambda s: (s["locator"], s["kind"]))

        documents = [
            self._document(request.project_key, doc_id)
            for doc_id in sorted(set(request.document_ids))
        ]
        music = []
        for music_id in sorted(set(request.music_ids), key=str):
            row = self.session.get(MusicReference, music_id)
            if row is None or row.removed_at is not None or row.project_key != request.project_key:
                raise CatalogNotFoundError(
                    "A music reference in the request is not in this project."
                )
            music.append(
                {
                    "id": str(row.id),
                    "track": row.track,
                    "artist": row.artist,
                    "reference": row.reference,
                    "episode": row.episode,
                    "scene": row.scene,
                    "mood": row.mood,
                    "intended_use": row.intended_use,
                }
            )
        package = None
        if request.chapter_package is not None:
            key, version = request.chapter_package
            row_package = self.session.execute(
                select(ChapterPackage).where(
                    ChapterPackage.project_key == request.project_key,
                    ChapterPackage.package_key == key,
                    ChapterPackage.version == version,
                )
            ).scalar_one_or_none()
            if row_package is None:
                raise CatalogNotFoundError("That chapter package version does not exist.")
            package = {
                "package_key": key,
                "version": version,
                "body_hash": row_package.body_hash,
                "approval_state": row_package.approval_state.value,
            }
            if row_package.approval_state.value != "APPROVED":
                warnings.append(
                    f"chapter package {key} v{version} is "
                    f"{row_package.approval_state.value}, not approved"
                )

        for ref in references.values():
            ref["roles"] = sorted(set(ref["roles"]))
        return {
            "schema": MANIFEST_SCHEMA,
            "project_key": request.project_key,
            "purpose": clean_text(request.purpose, 400, field="Purpose"),
            "characters": characters,
            "references": [references[k] for k in sorted(references)],
            "sources": sources,
            "documents": documents,
            "music": music,
            "chapter_package": package,
            "generation_settings": request.generation_settings,
            "warnings": sorted(set(warnings)),
        }

    # -- pieces ---------------------------------------------------------------
    def _reference(
        self, item: ReferenceItem, project_key: str, warnings: list[str]
    ) -> dict[str, Any]:
        region = region_of(item)
        provenance = item.provenance or {}
        if item.rights_status.value == "UNKNOWN":
            warnings.append(f"reference {item.id}: rights status unknown")
        if item.training_eligibility is not TrainingEligibility.APPROVED:
            warnings.append(
                f"reference {item.id}: not approved for model training "
                f"({item.training_eligibility.value})"
            )
        if item.reference_class.value == "UNSORTED":
            warnings.append(
                f"reference {item.id}: not sorted into canon/technique/continuity/mood yet"
            )
        standing = self.session.execute(
            select(ProjectReferenceStanding.standing)
            .where(
                ProjectReferenceStanding.reference_id == item.id,
                ProjectReferenceStanding.project_key == project_key,
            )
            .order_by(ProjectReferenceStanding.standing)
        ).scalars()
        return {
            "id": str(item.id),
            "locator": item.locator,
            "region": region.as_dict() if region is not None else None,
            "reference_class": item.reference_class.value,
            "origin": item.origin.value,
            "label": item.label,
            "collection": item.collection,
            "creator_handle": item.creator_handle,
            "rights_status": item.rights_status.value,
            "training_eligibility": item.training_eligibility.value,
            "project_standings": sorted({s.value for s in standing}),
            "provenance": {
                key: provenance[key]
                for key in (
                    "kind",
                    "source",
                    "collection",
                    "original_file_name",
                    "original_sha256",
                    "held_name",
                    "video_locator",
                    "posted_at",
                )
                if key in provenance
            },
            "roles": [],
        }

    def _unit(self, unit_id: uuid.UUID) -> tuple[CatalogUnit, CatalogEntry, CatalogMember | None]:
        found = self.session.execute(
            select(CatalogUnit, CatalogEntry, CatalogMember)
            .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
            .outerjoin(CatalogMember, CatalogMember.id == CatalogUnit.member_id)
            .where(CatalogUnit.id == unit_id)
        ).first()
        if found is None:
            raise CatalogNotFoundError("A source unit in the request is not in the catalog.")
        unit, entry, member = found
        if entry.status is not EntryStatus.CATALOGUED or entry.root_key != "source_vault":
            raise CatalogInputError("That source is not held in the Source Vault right now.")
        return unit, entry, member

    def _identity(self, unit: CatalogUnit, warnings: list[str]) -> dict[str, Any]:
        if unit.confidence is Confidence.LOW:
            warnings.append(
                f"unit {unit.id}: low-confidence identification ({'; '.join(unit.flags or [])})"
            )
        return {
            "unit_id": str(unit.id),
            "unit_key": unit.unit_key,
            "series_key": unit.series_key,
            "series_title": unit.series_title,
            "label": unit.label,
            "season": unit.season,
            "episode": unit.episode,
            "chapter_number": format(unit.chapter_number.normalize(), "f")
            if unit.chapter_number is not None
            else None,
            "confidence": unit.confidence.value,
        }

    def _page(self, page: SourcePage, warnings: list[str]) -> dict[str, Any]:
        unit, entry, _member = self._unit(page.unit_id)
        if unit.kind not in (UnitKind.MANGA_CHAPTER, UnitKind.ARCHIVE_PAGES):
            raise CatalogInputError("A source page must come from a chapter or a group of pages.")
        count = unit.page_count or 0
        if not 1 <= page.page <= count:
            raise CatalogInputError(f"That chapter has pages 1 to {count}.")
        sources = self._sources()
        index = (unit.first_page_index or 0) + page.page - 1
        try:
            held = sources.select(
                media_id_for(entry.relative_path),
                page_index=index,
                known_hash=self._known_hash(entry),
            )
        except SourceUnavailableError as exc:
            raise CatalogInputError(exc.user_message) from None
        return {
            "kind": "manga_page",
            "locator": held.locator.render(),
            "page": page.page,
            "archive_page_index": index,
            "archive": entry.file_name,
            "archive_sha256": held.content_hash,
            "note": clean_text(page.note, 400, field="Note"),
            **self._identity(unit, warnings),
        }

    def _moment(self, moment: SourceMoment, warnings: list[str]) -> dict[str, Any]:
        unit, entry, member = self._unit(moment.unit_id)
        if unit.kind not in (UnitKind.EPISODE, UnitKind.VIDEO):
            raise CatalogInputError("A source moment must come from an episode or a video.")
        if moment.time_ms < 0:
            raise CatalogInputError("A moment cannot be negative.")
        if member is None:
            try:
                held = self._sources().video_instant(
                    media_id_for(entry.relative_path),
                    moment.time_ms,
                    known_hash=self._known_hash(entry),
                )
            except SourceUnavailableError as exc:
                raise CatalogInputError(exc.user_message) from None
            locator, archive_hash = held.locator.render(), held.content_hash
        else:
            if (
                not entry.content_hash
                or entry.hashed_size != entry.byte_size
                or entry.hashed_mtime_ns != entry.mtime_ns
            ):
                raise CatalogInputError(
                    "That archive has not been hashed yet; run the catalog hash pass first.",
                    remediation="Start a catalog scan with hashing, then build the manifest again.",
                )
            from continuum_core import SourceLocator

            locator = SourceLocator.archive_instant(
                entry.content_hash, member.name, moment.time_ms
            ).render()
            archive_hash = entry.content_hash
        return {
            "kind": "anime_moment",
            "locator": locator,
            "time_ms": moment.time_ms,
            "archive": entry.file_name,
            "member": member.name if member is not None else None,
            "file_sha256": archive_hash,
            "note": clean_text(moment.note, 400, field="Note"),
            **self._identity(unit, warnings),
        }

    def _document(self, project_key: str, document_id: str) -> dict[str, Any]:
        if self.projects is None:
            raise CatalogInputError("Projects are not configured.")
        found = self.projects.document(project_key, document_id)
        if found is None:
            raise CatalogNotFoundError("A project document in the request does not exist.")
        _project, document, markdown = found
        return {
            "id": document.id,
            "title": document.title,
            "lifecycle": document.lifecycle,
            "maturity": document.maturity,
            "authority": document.authority,
            "version": document.version,
            "episode": document.episode,
            "sha256": content_hash_bytes(markdown.encode("utf-8")),
        }

    def _sources(self) -> Any:
        if self.catalog.sources is None:
            raise CatalogInputError("The Source Vault is not configured.")
        return self.catalog.sources

    @staticmethod
    def _known_hash(entry: CatalogEntry) -> Any:
        def known(relative: str, size: int, mtime_ns: int) -> str | None:
            if (
                relative == entry.relative_path
                and entry.content_hash
                and entry.hashed_size == size
                and entry.hashed_mtime_ns == mtime_ns
            ):
                return entry.content_hash
            return None

        return known

    # -- reading --------------------------------------------------------------
    def get(self, manifest_id: uuid.UUID) -> ReferenceManifest:
        row = self.session.get(ReferenceManifest, manifest_id)
        if row is None:
            raise CatalogNotFoundError("That manifest does not exist.")
        return row

    def for_project(self, project_key: str) -> list[ReferenceManifest]:
        require_project_key(project_key)
        return list(
            self.session.execute(
                select(ReferenceManifest)
                .where(ReferenceManifest.project_key == project_key)
                .order_by(ReferenceManifest.created_at.desc(), ReferenceManifest.id.desc())
            ).scalars()
        )


def manifest_view(row: ReferenceManifest, *, full: bool = True) -> dict[str, Any]:
    manifest = row.manifest or {}
    view: dict[str, Any] = {
        "id": str(row.id),
        "project_key": row.project_key,
        "label": row.label,
        "manifest_hash": row.manifest_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "counts": {
            key: len(manifest.get(key) or [])
            for key in ("characters", "references", "sources", "documents", "music", "warnings")
        },
    }
    if full:
        view["request"] = row.request
        view["manifest"] = manifest
    return view
