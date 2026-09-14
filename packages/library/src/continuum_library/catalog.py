"""The reference catalog: characters, outfits, visual modes and references.

Rules this service enforces - in code, below the API, so every caller gets them:

* **Bytes are addressed by content.** A reference names a
  :class:`~continuum_core.SourceLocator`; a crop is a region beside it. Held
  media is never copied - its location is an observation, verified on read.
* **Removing a record never touches the source.** References, characters and
  outfits are soft-deleted; the file they describe stays exactly where it was.
* **Identity, wardrobe, acting and technique stay separate.** A character link
  names an aspect; a technique link names a facet and optionally a visual mode.
  A visual mode reaches a character only through a project-scoped assignment.
* **Manual first, honestly labelled.** Descriptors a person adds are ``USER``;
  only an analyzer (later) may add ``ANALYSIS`` descriptors, with its name.
* **Fan art stays fan art.** Origin is recorded explicitly and never inferred.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from continuum_core import NormalizedRegion, fanout_segments, is_sha256_hex
from continuum_core.references import (
    AssetMedium,
    AssetOrigin,
    CharacterAspect,
    CharacterOrigin,
    DescriptorFacet,
    DescriptorOrigin,
    ModeScope,
    ModeTrigger,
    OutfitKind,
    PanelSourceRole,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    SubjectKind,
    TechniqueFacet,
    VisualModeCategory,
)
from continuum_db.models import (
    CharacterOutfit,
    CharacterProfile,
    LibraryAsset,
    LibraryAssetLocation,
    ProjectPanelSource,
    ProjectReferenceStanding,
    ProjectVisualModeAssignment,
    ReferenceCharacter,
    ReferenceDescriptor,
    ReferenceItem,
    ReferenceTechnique,
    ReferenceUseLink,
    VisualMode,
)
from continuum_imaging import EncodedImage, open_image, preview, working_rendition
from continuum_storage import (
    DerivedStore,
    SourceAccess,
    SourceChangedError,
    SourceUnavailableError,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from continuum_library.validation import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    clean_handle,
    clean_text,
    clean_url,
    require_episode,
    require_project_key,
)

__all__ = [
    "MAX_UPLOAD_IMAGE_BYTES",
    "CharacterLink",
    "DescriptorSpec",
    "PanelSourceSpec",
    "ReferenceCatalog",
    "ReferenceSpec",
    "StandingSpec",
    "StoredImage",
    "TechniqueLink",
]

MAX_UPLOAD_IMAGE_BYTES = 64 * 1024 * 1024
#: Origins a person may declare. Generated and project-approved references are
#: created by production, never typed in.
USER_DECLARED_ORIGINS = frozenset(
    {
        ReferenceOrigin.SOURCE,
        ReferenceOrigin.OFFICIAL_ART,
        ReferenceOrigin.FAN_ART,
        ReferenceOrigin.USER_CREATED,
    }
)
LIBRARY_ROOT = "library"
GENERATED_ROOT = "generated"


@dataclass(frozen=True, slots=True)
class CharacterLink:
    character_id: uuid.UUID
    aspect: CharacterAspect
    outfit_id: uuid.UUID | None = None
    preferred: bool = False
    notes: str = ""


@dataclass(frozen=True, slots=True)
class TechniqueLink:
    facet: TechniqueFacet
    visual_mode_id: uuid.UUID | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class DescriptorSpec:
    facet: DescriptorFacet
    value: str


@dataclass(frozen=True, slots=True)
class StandingSpec:
    project_key: str
    standing: ProjectStanding
    character_id: uuid.UUID | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class PanelSourceSpec:
    project_key: str
    episode: str
    page: int
    role: PanelSourceRole
    chapter: int | None = None
    panel: int | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class StoredImage:
    """Image bytes landed under the library root.

    ``asset`` is what references and previews use. For a format kept only as an
    original (HEIC/HEIF), ``original`` is the untouched uploaded bytes and
    ``conversion`` records their hash, format and the decoder that produced the
    deterministic PNG in ``asset``.
    """

    asset: LibraryAsset
    original: LibraryAsset | None = None
    conversion: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReferenceSpec:
    """Everything a user decides when adding a reference, in one step."""

    reference_class: ReferenceClass
    origin: ReferenceOrigin
    label: str = ""
    notes: str = ""
    favorite: bool = False
    region: NormalizedRegion | None = None
    source_url: str | None = None
    creator_handle: str | None = None
    uses: tuple[ReferenceUse, ...] = ()
    characters: tuple[CharacterLink, ...] = ()
    techniques: tuple[TechniqueLink, ...] = ()
    descriptors: tuple[DescriptorSpec, ...] = ()
    standings: tuple[StandingSpec, ...] = ()
    panel_sources: tuple[PanelSourceSpec, ...] = ()
    extra_provenance: dict[str, Any] = field(default_factory=dict)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class ReferenceCatalog:
    """Catalog operations inside one database session (the caller commits)."""

    def __init__(
        self,
        session: Session,
        *,
        sources: SourceAccess | None = None,
        derived: DerivedStore | None = None,
    ) -> None:
        self.session = session
        self.sources = sources
        self.derived = derived

    # =====================================================================
    # Assets and locations (Tier A)
    # =====================================================================
    def known_hash(self, relative: str, size: int, mtime_ns: int) -> str | None:
        """A content hash already recorded for this exact observation, if any."""
        return self.session.execute(
            select(LibraryAsset.content_hash)
            .join(LibraryAssetLocation, LibraryAssetLocation.asset_id == LibraryAsset.id)
            .where(
                LibraryAssetLocation.root_key == "source_vault",
                LibraryAssetLocation.relative_path == relative,
                LibraryAssetLocation.byte_size == size,
                LibraryAssetLocation.mtime_ns == mtime_ns,
            )
            .limit(1)
        ).scalar_one_or_none()

    def asset(
        self, content_hash: str, medium: AssetMedium, origin: AssetOrigin, byte_size: int
    ) -> LibraryAsset:
        """The asset for these bytes, created once even under concurrent requests."""
        existing = self.session.execute(
            select(LibraryAsset).where(LibraryAsset.content_hash == content_hash)
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        try:
            with self.session.begin_nested():
                created = LibraryAsset(
                    content_hash=content_hash, medium=medium, origin=origin, byte_size=byte_size
                )
                self.session.add(created)
                self.session.flush()
            return created
        except IntegrityError:
            return self.session.execute(
                select(LibraryAsset).where(LibraryAsset.content_hash == content_hash)
            ).scalar_one()

    def observe(
        self, asset: LibraryAsset, root_key: str, relative: str, size: int, mtime_ns: int
    ) -> LibraryAssetLocation:
        existing = self.session.execute(
            select(LibraryAssetLocation).where(
                LibraryAssetLocation.root_key == root_key,
                LibraryAssetLocation.relative_path == relative,
                LibraryAssetLocation.byte_size == size,
                LibraryAssetLocation.mtime_ns == mtime_ns,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        try:
            with self.session.begin_nested():
                location = LibraryAssetLocation(
                    asset_id=asset.id,
                    root_key=root_key,
                    relative_path=relative,
                    byte_size=size,
                    mtime_ns=mtime_ns,
                )
                self.session.add(location)
                self.session.flush()
            return location
        except IntegrityError:
            return self.session.execute(
                select(LibraryAssetLocation).where(
                    LibraryAssetLocation.root_key == root_key,
                    LibraryAssetLocation.relative_path == relative,
                    LibraryAssetLocation.byte_size == size,
                    LibraryAssetLocation.mtime_ns == mtime_ns,
                )
            ).scalar_one()

    def store_bytes(
        self, data: bytes, *, root_key: str, medium: AssetMedium, origin: AssetOrigin
    ) -> LibraryAsset:
        """Land user-added or generated bytes content-addressed and record them."""
        if self.derived is None:
            raise CatalogInputError("Writable storage is not configured.")
        stored = self.derived.put_bytes(root_key, data)
        asset = self.asset(stored.content_hash, medium, origin, stored.size_bytes)
        shard, name = fanout_segments(stored.content_hash)
        self.observe(asset, root_key, f"{shard}/{name}", stored.size_bytes, 0)
        return asset

    def locations(self, asset_id: uuid.UUID) -> list[LibraryAssetLocation]:
        return list(
            self.session.execute(
                select(LibraryAssetLocation)
                .where(LibraryAssetLocation.asset_id == asset_id)
                .order_by(LibraryAssetLocation.observed_at.desc(), LibraryAssetLocation.id.desc())
            ).scalars()
        )

    # =====================================================================
    # Characters and outfits (Tier B)
    # =====================================================================
    def create_character(
        self,
        display_name: str,
        *,
        subject_kind: SubjectKind = SubjectKind.CHARACTER,
        source_label: str = "",
        summary: str = "",
        scale_notes: str = "",
        distinguishing_marks: str = "",
        posture_notes: str = "",
        notes: str = "",
        origin: CharacterOrigin = CharacterOrigin.SOURCE_WORK,
        project_key: str | None = None,
        design_documents: tuple[str, ...] | list[str] = (),
    ) -> CharacterProfile:
        name = clean_text(display_name, 200, field="Name")
        if not name:
            raise CatalogInputError("A character needs a name.")
        origin, project_key, documents = _character_origin(origin, project_key, design_documents)
        character = CharacterProfile(
            display_name=name,
            subject_kind=subject_kind,
            origin=origin,
            project_key=project_key,
            design_documents=documents,
            source_label=clean_text(source_label, 200, field="Source"),
            summary=clean_text(summary, 4000, field="Summary"),
            scale_notes=clean_text(scale_notes, 4000, field="Scale notes"),
            distinguishing_marks=clean_text(distinguishing_marks, 4000, field="Marks"),
            posture_notes=clean_text(posture_notes, 4000, field="Posture notes"),
            notes=clean_text(notes, 8000, field="Notes"),
        )
        self.session.add(character)
        self.session.flush()
        return character

    def character(
        self, character_id: uuid.UUID, *, include_removed: bool = False
    ) -> CharacterProfile:
        found = self.session.get(CharacterProfile, character_id)
        if found is None or (found.removed_at is not None and not include_removed):
            raise CatalogNotFoundError("That character does not exist.")
        return found

    def list_characters(self, subject_kind: SubjectKind | None = None) -> list[CharacterProfile]:
        query = select(CharacterProfile).where(CharacterProfile.removed_at.is_(None))
        if subject_kind is not None:
            query = query.where(CharacterProfile.subject_kind == subject_kind)
        return list(
            self.session.execute(
                query.order_by(func.lower(CharacterProfile.display_name))
            ).scalars()
        )

    def update_character(
        self, character_id: uuid.UUID, row_version: int, **changes: Any
    ) -> CharacterProfile:
        character = self.character(character_id)
        self._check_version(character.row_version, row_version)
        limits = {
            "display_name": 200,
            "source_label": 200,
            "summary": 4000,
            "scale_notes": 4000,
            "distinguishing_marks": 4000,
            "posture_notes": 4000,
            "notes": 8000,
        }
        if {"origin", "project_key", "design_documents"} & set(changes):
            origin, project_key, documents = _character_origin(
                changes.pop("origin", character.origin),
                changes.pop("project_key", character.project_key),
                changes.pop("design_documents", character.design_documents),
            )
            character.origin = origin
            character.project_key = project_key
            character.design_documents = documents
        for key, value in changes.items():
            if key == "subject_kind":
                character.subject_kind = SubjectKind(value)
            elif key in limits:
                cleaned = clean_text(value, limits[key], field=key)
                if key == "display_name" and not cleaned:
                    raise CatalogInputError("A character needs a name.")
                setattr(character, key, cleaned)
            else:
                raise CatalogInputError(f"'{key}' cannot be changed.")
        self._flush()
        return character

    def remove_character(self, character_id: uuid.UUID, row_version: int) -> None:
        character = self.character(character_id)
        self._check_version(character.row_version, row_version)
        character.removed_at = _now()
        self._flush()

    def create_outfit(
        self,
        character_id: uuid.UUID,
        name: str,
        *,
        kind: OutfitKind = OutfitKind.SOURCE_DEFAULT,
        project_key: str | None = None,
        era: str = "",
        season_weather: str = "",
        condition: str = "",
        notes: str = "",
    ) -> CharacterOutfit:
        self.character(character_id)
        title = clean_text(name, 200, field="Outfit name")
        if not title:
            raise CatalogInputError("An outfit needs a name.")
        if kind is OutfitKind.PROJECT:
            if project_key is None:
                raise CatalogInputError("A project outfit names its project.")
            require_project_key(project_key)
        elif project_key is not None:
            raise CatalogInputError("Only a project outfit belongs to a project.")
        outfit = CharacterOutfit(
            character_id=character_id,
            name=title,
            kind=kind,
            project_key=project_key,
            era=clean_text(era, 120, field="Era"),
            season_weather=clean_text(season_weather, 120, field="Season/weather"),
            condition=clean_text(condition, 120, field="Condition"),
            notes=clean_text(notes, 8000, field="Notes"),
        )
        self.session.add(outfit)
        self.session.flush()
        return outfit

    def outfit(self, outfit_id: uuid.UUID) -> CharacterOutfit:
        found = self.session.get(CharacterOutfit, outfit_id)
        if found is None or found.removed_at is not None:
            raise CatalogNotFoundError("That outfit does not exist.")
        return found

    def outfits(self, character_id: uuid.UUID) -> list[CharacterOutfit]:
        return list(
            self.session.execute(
                select(CharacterOutfit)
                .where(
                    CharacterOutfit.character_id == character_id,
                    CharacterOutfit.removed_at.is_(None),
                )
                .order_by(CharacterOutfit.created_at, CharacterOutfit.id)
            ).scalars()
        )

    def update_outfit(
        self, outfit_id: uuid.UUID, row_version: int, **changes: Any
    ) -> CharacterOutfit:
        outfit = self.outfit(outfit_id)
        self._check_version(outfit.row_version, row_version)
        limits = {"name": 200, "era": 120, "season_weather": 120, "condition": 120, "notes": 8000}
        for key, value in changes.items():
            if key not in limits:
                raise CatalogInputError(f"'{key}' cannot be changed.")
            cleaned = clean_text(value, limits[key], field=key)
            if key == "name" and not cleaned:
                raise CatalogInputError("An outfit needs a name.")
            setattr(outfit, key, cleaned)
        self._flush()
        return outfit

    def remove_outfit(self, outfit_id: uuid.UUID, row_version: int) -> None:
        outfit = self.outfit(outfit_id)
        self._check_version(outfit.row_version, row_version)
        outfit.removed_at = _now()
        self._flush()

    # =====================================================================
    # Visual modes and their project scopes
    # =====================================================================
    def create_visual_mode(
        self, name: str, category: VisualModeCategory, *, description: str = "", notes: str = ""
    ) -> VisualMode:
        title = clean_text(name, 200, field="Mode name")
        if not title:
            raise CatalogInputError("A visual mode needs a name.")
        mode = VisualMode(
            name=title,
            category=category,
            description=clean_text(description, 8000, field="Description"),
            notes=clean_text(notes, 8000, field="Notes"),
        )
        self.session.add(mode)
        self.session.flush()
        return mode

    def visual_mode(self, mode_id: uuid.UUID) -> VisualMode:
        found = self.session.get(VisualMode, mode_id)
        if found is None or found.removed_at is not None:
            raise CatalogNotFoundError("That visual mode does not exist.")
        return found

    def list_visual_modes(self) -> list[VisualMode]:
        return list(
            self.session.execute(
                select(VisualMode)
                .where(VisualMode.removed_at.is_(None))
                .order_by(VisualMode.category, func.lower(VisualMode.name))
            ).scalars()
        )

    def update_visual_mode(
        self, mode_id: uuid.UUID, row_version: int, **changes: Any
    ) -> VisualMode:
        mode = self.visual_mode(mode_id)
        self._check_version(mode.row_version, row_version)
        for key, value in changes.items():
            if key == "category":
                mode.category = VisualModeCategory(value)
            elif key in ("name", "description", "notes"):
                cleaned = clean_text(value, 200 if key == "name" else 8000, field=key)
                if key == "name" and not cleaned:
                    raise CatalogInputError("A visual mode needs a name.")
                setattr(mode, key, cleaned)
            else:
                raise CatalogInputError(f"'{key}' cannot be changed.")
        self._flush()
        return mode

    def remove_visual_mode(self, mode_id: uuid.UUID, row_version: int) -> None:
        mode = self.visual_mode(mode_id)
        self._check_version(mode.row_version, row_version)
        mode.removed_at = _now()
        self._flush()

    def assign_visual_mode(
        self,
        project_key: str,
        visual_mode_id: uuid.UUID,
        scope: ModeScope,
        *,
        trigger: ModeTrigger = ModeTrigger.DIRECTORIAL,
        episode: str | None = None,
        scene: int | None = None,
        page_from: int | None = None,
        page_to: int | None = None,
        panel: int | None = None,
        event_label: str | None = None,
        character_id: uuid.UUID | None = None,
        notes: str = "",
    ) -> ProjectVisualModeAssignment:
        """Apply a mode to a scope of a project. The character, if any, is only
        *who the mode acts on here*; their identity record is not touched."""
        require_project_key(project_key)
        self.visual_mode(visual_mode_id)
        if episode is not None:
            require_episode(episode)
        if character_id is not None:
            self.character(character_id)
        required = {
            ModeScope.EPISODE: episode is not None,
            ModeScope.SCENE: episode is not None and scene is not None,
            ModeScope.SEQUENCE: episode is not None
            and page_from is not None
            and page_to is not None
            and page_to >= page_from,
            ModeScope.PANEL: episode is not None and page_from is not None and panel is not None,
            ModeScope.EVENT: bool(event_label and event_label.strip()),
        }
        if not required[scope]:
            raise CatalogInputError(f"A {scope.value.lower()} assignment is missing its target.")
        if trigger is ModeTrigger.CHARACTER_CONTROLLED and character_id is None:
            raise CatalogInputError("A character-controlled form names the character.")
        assignment = ProjectVisualModeAssignment(
            project_key=project_key,
            visual_mode_id=visual_mode_id,
            scope=scope,
            trigger=trigger,
            episode=episode,
            scene=scene,
            page_from=page_from,
            page_to=page_to,
            panel=panel,
            event_label=clean_text(event_label, 200, field="Event") if event_label else None,
            character_id=character_id,
            notes=clean_text(notes, 4000, field="Notes"),
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def assignments(
        self, project_key: str, *, episode: str | None = None
    ) -> list[ProjectVisualModeAssignment]:
        require_project_key(project_key)
        query = select(ProjectVisualModeAssignment).where(
            ProjectVisualModeAssignment.project_key == project_key
        )
        if episode is not None:
            query = query.where(
                or_(
                    ProjectVisualModeAssignment.episode == episode,
                    ProjectVisualModeAssignment.episode.is_(None),
                )
            )
        return list(
            self.session.execute(
                query.order_by(
                    ProjectVisualModeAssignment.created_at, ProjectVisualModeAssignment.id
                )
            ).scalars()
        )

    def remove_assignment(self, assignment_id: uuid.UUID) -> None:
        found = self.session.get(ProjectVisualModeAssignment, assignment_id)
        if found is None:
            raise CatalogNotFoundError("That assignment does not exist.")
        self.session.delete(found)
        self.session.flush()

    def modes_in_effect(
        self,
        project_key: str,
        episode: str,
        page: int,
        panel: int | None = None,
        *,
        scene: int | None = None,
    ) -> list[ProjectVisualModeAssignment]:
        """Assignments whose scope covers this page/panel, broadest first."""
        order = {
            ModeScope.EPISODE: 0,
            ModeScope.SCENE: 1,
            ModeScope.SEQUENCE: 2,
            ModeScope.PANEL: 3,
            ModeScope.EVENT: 4,
        }
        applicable = []
        for assignment in self.assignments(project_key, episode=episode):
            covers = (
                (assignment.scope is ModeScope.EPISODE and assignment.episode == episode)
                or (
                    assignment.scope is ModeScope.SCENE
                    and assignment.episode == episode
                    and scene is not None
                    and assignment.scene == scene
                )
                or (
                    assignment.scope is ModeScope.SEQUENCE
                    and assignment.episode == episode
                    and (assignment.page_from or 0) <= page <= (assignment.page_to or 0)
                )
                or (
                    assignment.scope is ModeScope.PANEL
                    and assignment.episode == episode
                    and assignment.page_from == page
                    and assignment.panel == panel
                )
            )
            if covers:
                applicable.append(assignment)
        return sorted(applicable, key=lambda a: order[a.scope])

    # =====================================================================
    # References (Tier B)
    # =====================================================================
    def add_from_source(
        self,
        media_id: str,
        spec: ReferenceSpec,
        *,
        page_index: int | None = None,
        pdf_page: int | None = None,
    ) -> ReferenceItem:
        """A reference to one page, image or PDF page of held media - or a region of it."""
        sources = self._require_sources()
        try:
            unit = sources.select(
                media_id, page_index=page_index, pdf_page=pdf_page, known_hash=self.known_hash
            )
        except SourceUnavailableError as exc:
            raise CatalogInputError(
                exc.user_message, technical_detail=exc.technical_detail
            ) from None
        if spec.region is not None and unit.medium is AssetMedium.PDF:
            raise CatalogInputError(
                "Regions of PDF pages are not supported yet; reference the whole page."
            )
        self._check_user_origin(spec.origin)
        asset = self.asset(unit.content_hash, unit.medium, AssetOrigin.SOURCE_VAULT, unit.byte_size)
        self.observe(asset, "source_vault", unit.relative, unit.byte_size, unit.mtime_ns)
        provenance = {
            "kind": "source_locator",
            "locator": unit.locator.render(),
            "held_name": unit.name,
            "selected_index": unit.unit_index,
            **spec.extra_provenance,
        }
        return self._create_reference(
            asset, unit.locator.render(), unit.unit_index, spec, provenance
        )

    def add_from_frame(
        self, media_id: str, time_ms: int, image: bytes, spec: ReferenceSpec
    ) -> ReferenceItem:
        """A frame captured from held video. The frame is stored; the video is not
        copied - the reference records the video's locator and instant."""
        sources = self._require_sources()
        try:
            instant = sources.video_instant(media_id, time_ms, known_hash=self.known_hash)
        except SourceUnavailableError as exc:
            raise CatalogInputError(exc.user_message) from None
        video = self.asset(
            instant.content_hash, AssetMedium.VIDEO, AssetOrigin.SOURCE_VAULT, instant.byte_size
        )
        self.observe(video, "source_vault", instant.relative, instant.byte_size, instant.mtime_ns)
        frame = self._store_image(image)
        extra: dict[str, Any] = {
            "kind": "source_frame",
            "video_locator": instant.locator.render(),
            "held_name": instant.name,
            **spec.extra_provenance,
        }
        if frame.conversion:
            extra["conversion"] = frame.conversion
        self._check_user_origin(spec.origin)
        return self._create_reference(
            frame.asset, self._image_locator(frame.asset), None, spec, extra
        )

    def add_upload(self, image: bytes, spec: ReferenceSpec) -> ReferenceItem:
        """A user-added image: official art, fan art, a screenshot, a sketch."""
        self._check_user_origin(spec.origin)
        stored = self._store_image(image)
        provenance: dict[str, Any] = {
            "kind": "user_assertion",
            "intake": "upload",
            **spec.extra_provenance,
        }
        if stored.conversion:
            provenance["conversion"] = stored.conversion
        return self._create_reference(
            stored.asset, self._image_locator(stored.asset), None, spec, provenance
        )

    def add_existing_image(
        self, asset: LibraryAsset, spec: ReferenceSpec, provenance: dict[str, Any]
    ) -> ReferenceItem:
        """A reference to image bytes already stored (the inbox's accept step)."""
        if asset.medium is not AssetMedium.IMAGE:
            raise CatalogInputError("Only an image can become a reference directly.")
        self._check_user_origin(spec.origin)
        return self._create_reference(asset, self._image_locator(asset), None, spec, provenance)

    def add_generated(
        self, content_hash: str, spec: ReferenceSpec, provenance: dict[str, Any]
    ) -> ReferenceItem:
        """A continuity reference to approved generated output (production only)."""
        if spec.origin not in (ReferenceOrigin.GENERATED, ReferenceOrigin.PROJECT_APPROVED):
            raise CatalogInputError("Generated references carry a generated origin.")
        asset = self.session.execute(
            select(LibraryAsset).where(LibraryAsset.content_hash == content_hash)
        ).scalar_one_or_none()
        if asset is None:
            raise CatalogNotFoundError("Those generated bytes are not recorded.")
        locator = f"gen:sha256:{content_hash}"
        return self._create_reference(asset, locator, None, spec, provenance)

    def reference(self, reference_id: uuid.UUID, *, include_removed: bool = False) -> ReferenceItem:
        found = self.session.get(ReferenceItem, reference_id)
        if found is None or (found.removed_at is not None and not include_removed):
            raise CatalogNotFoundError("That reference does not exist.")
        return found

    def update_reference(
        self, reference_id: uuid.UUID, row_version: int, **changes: Any
    ) -> ReferenceItem:
        item = self.reference(reference_id)
        self._check_version(item.row_version, row_version)
        for key, value in changes.items():
            if key == "label":
                item.label = clean_text(value, 300, field="Label")
            elif key == "notes":
                item.notes = clean_text(value, 8000, field="Notes")
            elif key == "favorite":
                item.favorite = bool(value)
            elif key == "reference_class":
                item.reference_class = ReferenceClass(value)
            elif key == "origin":
                origin = ReferenceOrigin(value)
                if item.origin in (ReferenceOrigin.GENERATED, ReferenceOrigin.PROJECT_APPROVED):
                    raise CatalogInputError("A generated reference keeps its origin.")
                self._check_user_origin(origin)
                item.origin = origin
            elif key == "source_url":
                item.source_url = clean_url(value)
            elif key == "creator_handle":
                item.creator_handle = clean_handle(value)
            else:
                raise CatalogInputError(
                    f"'{key}' cannot be changed; select a new reference instead."
                )
        self._flush()
        return item

    def remove_reference(self, reference_id: uuid.UUID, row_version: int) -> None:
        """Soft-delete the catalog record. The source file is not touched."""
        item = self.reference(reference_id)
        self._check_version(item.row_version, row_version)
        item.removed_at = _now()
        self._flush()

    def set_uses(
        self, reference_id: uuid.UUID, uses: Iterable[ReferenceUse]
    ) -> list[ReferenceUseLink]:
        item = self.reference(reference_id)
        wanted = list(dict.fromkeys(ReferenceUse(u) for u in uses))
        existing = {
            link.use: link
            for link in self.session.execute(
                select(ReferenceUseLink).where(ReferenceUseLink.reference_id == item.id)
            ).scalars()
        }
        for use, link in existing.items():
            if use not in wanted:
                self.session.delete(link)
        for use in wanted:
            if use not in existing:
                self.session.add(ReferenceUseLink(reference_id=item.id, use=use))
        self.session.flush()
        return self.uses(item.id)

    def uses(self, reference_id: uuid.UUID) -> list[ReferenceUseLink]:
        return list(
            self.session.execute(
                select(ReferenceUseLink)
                .where(ReferenceUseLink.reference_id == reference_id)
                .order_by(ReferenceUseLink.use)
            ).scalars()
        )

    def link_character(self, reference_id: uuid.UUID, link: CharacterLink) -> ReferenceCharacter:
        item = self.reference(reference_id)
        self.character(link.character_id)
        if (
            link.outfit_id is not None
            and self.outfit(link.outfit_id).character_id != link.character_id
        ):
            raise CatalogInputError("That outfit belongs to a different character.")
        existing = self.session.execute(
            select(ReferenceCharacter).where(
                ReferenceCharacter.reference_id == item.id,
                ReferenceCharacter.character_id == link.character_id,
                ReferenceCharacter.aspect == link.aspect,
                ReferenceCharacter.outfit_id.is_(None)
                if link.outfit_id is None
                else ReferenceCharacter.outfit_id == link.outfit_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.preferred = link.preferred
            existing.notes = clean_text(link.notes, 4000, field="Notes")
            self.session.flush()
            return existing
        row = ReferenceCharacter(
            reference_id=item.id,
            character_id=link.character_id,
            outfit_id=link.outfit_id,
            aspect=link.aspect,
            preferred=link.preferred,
            notes=clean_text(link.notes, 4000, field="Notes"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def set_preferred(self, link_id: uuid.UUID, preferred: bool) -> ReferenceCharacter:
        link = self.session.get(ReferenceCharacter, link_id)
        if link is None:
            raise CatalogNotFoundError("That character link does not exist.")
        link.preferred = preferred
        self.session.flush()
        return link

    def unlink_character(self, link_id: uuid.UUID) -> None:
        link = self.session.get(ReferenceCharacter, link_id)
        if link is None:
            raise CatalogNotFoundError("That character link does not exist.")
        self.session.delete(link)
        self.session.flush()

    def link_technique(self, reference_id: uuid.UUID, link: TechniqueLink) -> ReferenceTechnique:
        item = self.reference(reference_id)
        if link.visual_mode_id is not None:
            self.visual_mode(link.visual_mode_id)
        existing = self.session.execute(
            select(ReferenceTechnique).where(
                ReferenceTechnique.reference_id == item.id,
                ReferenceTechnique.facet == link.facet,
                ReferenceTechnique.visual_mode_id.is_(None)
                if link.visual_mode_id is None
                else ReferenceTechnique.visual_mode_id == link.visual_mode_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.notes = clean_text(link.notes, 4000, field="Notes")
            self.session.flush()
            return existing
        row = ReferenceTechnique(
            reference_id=item.id,
            visual_mode_id=link.visual_mode_id,
            facet=link.facet,
            notes=clean_text(link.notes, 4000, field="Notes"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def unlink_technique(self, link_id: uuid.UUID) -> None:
        link = self.session.get(ReferenceTechnique, link_id)
        if link is None:
            raise CatalogNotFoundError("That technique link does not exist.")
        self.session.delete(link)
        self.session.flush()

    def add_descriptor(
        self,
        reference_id: uuid.UUID,
        spec: DescriptorSpec,
        *,
        origin: DescriptorOrigin = DescriptorOrigin.USER,
        analyzer_ref: str | None = None,
        confidence: float | None = None,
    ) -> ReferenceDescriptor:
        item = self.reference(reference_id)
        value = clean_text(spec.value, 200, field="Value")
        if not value:
            raise CatalogInputError("A descriptor needs a value.")
        if origin is DescriptorOrigin.USER and (analyzer_ref or confidence is not None):
            raise CatalogInputError("A user tag carries no analyzer or confidence.")
        if origin is DescriptorOrigin.ANALYSIS and not analyzer_ref:
            raise CatalogInputError("An analysis descriptor names its analyzer.")
        existing = self.session.execute(
            select(ReferenceDescriptor).where(
                ReferenceDescriptor.reference_id == item.id,
                ReferenceDescriptor.facet == spec.facet,
                ReferenceDescriptor.value == value,
                ReferenceDescriptor.origin == origin,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = ReferenceDescriptor(
            reference_id=item.id,
            facet=spec.facet,
            value=value,
            origin=origin,
            analyzer_ref=analyzer_ref,
            confidence=confidence,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def remove_descriptor(self, descriptor_id: uuid.UUID) -> None:
        row = self.session.get(ReferenceDescriptor, descriptor_id)
        if row is None:
            raise CatalogNotFoundError("That descriptor does not exist.")
        self.session.delete(row)
        self.session.flush()

    def set_standing(self, reference_id: uuid.UUID, spec: StandingSpec) -> ProjectReferenceStanding:
        item = self.reference(reference_id)
        require_project_key(spec.project_key)
        if spec.character_id is not None:
            self.character(spec.character_id)
        existing = self.session.execute(
            select(ProjectReferenceStanding).where(
                ProjectReferenceStanding.project_key == spec.project_key,
                ProjectReferenceStanding.reference_id == item.id,
                ProjectReferenceStanding.standing == spec.standing,
                ProjectReferenceStanding.character_id.is_(None)
                if spec.character_id is None
                else ProjectReferenceStanding.character_id == spec.character_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.notes = clean_text(spec.notes, 4000, field="Notes")
            self.session.flush()
            return existing
        row = ProjectReferenceStanding(
            project_key=spec.project_key,
            reference_id=item.id,
            character_id=spec.character_id,
            standing=spec.standing,
            notes=clean_text(spec.notes, 4000, field="Notes"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def remove_standing(self, standing_id: uuid.UUID) -> None:
        row = self.session.get(ProjectReferenceStanding, standing_id)
        if row is None:
            raise CatalogNotFoundError("That standing does not exist.")
        self.session.delete(row)
        self.session.flush()

    def add_panel_source(
        self, reference_id: uuid.UUID, spec: PanelSourceSpec
    ) -> ProjectPanelSource:
        item = self.reference(reference_id)
        require_project_key(spec.project_key)
        require_episode(spec.episode)
        if spec.page < 1 or (spec.panel is not None and spec.panel < 1):
            raise CatalogInputError("Pages and panels are numbered from 1.")
        if spec.chapter is not None and spec.chapter < 1:
            raise CatalogInputError("Chapters are numbered from 1.")
        if spec.role is PanelSourceRole.SOURCE_PLATE and item.locator.startswith("pdf:"):
            raise CatalogInputError("A PDF page cannot be a source plate yet.")
        existing = self.session.execute(
            select(ProjectPanelSource).where(
                ProjectPanelSource.project_key == spec.project_key,
                ProjectPanelSource.episode == spec.episode,
                ProjectPanelSource.page == spec.page,
                ProjectPanelSource.panel.is_(None)
                if spec.panel is None
                else ProjectPanelSource.panel == spec.panel,
                ProjectPanelSource.reference_id == item.id,
                ProjectPanelSource.role == spec.role,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        row = ProjectPanelSource(
            project_key=spec.project_key,
            episode=spec.episode,
            chapter=spec.chapter,
            page=spec.page,
            panel=spec.panel,
            reference_id=item.id,
            role=spec.role,
            notes=clean_text(spec.notes, 4000, field="Notes"),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def remove_panel_source(self, panel_source_id: uuid.UUID) -> None:
        row = self.session.get(ProjectPanelSource, panel_source_id)
        if row is None:
            raise CatalogNotFoundError("That scene source does not exist.")
        self.session.delete(row)
        self.session.flush()

    def panel_sources(
        self, project_key: str, *, episode: str | None = None, page: int | None = None
    ) -> list[ProjectPanelSource]:
        require_project_key(project_key)
        query = (
            select(ProjectPanelSource)
            .join(ReferenceItem, ReferenceItem.id == ProjectPanelSource.reference_id)
            .where(
                ProjectPanelSource.project_key == project_key, ReferenceItem.removed_at.is_(None)
            )
        )
        if episode is not None:
            query = query.where(ProjectPanelSource.episode == episode)
        if page is not None:
            query = query.where(ProjectPanelSource.page == page)
        return list(
            self.session.execute(
                query.order_by(
                    ProjectPanelSource.episode, ProjectPanelSource.page, ProjectPanelSource.panel
                )
            ).scalars()
        )

    def list_references(
        self,
        *,
        character_id: uuid.UUID | None = None,
        aspect: CharacterAspect | None = None,
        outfit_id: uuid.UUID | None = None,
        visual_mode_id: uuid.UUID | None = None,
        facet: TechniqueFacet | None = None,
        use: ReferenceUse | None = None,
        reference_class: ReferenceClass | None = None,
        origin: ReferenceOrigin | None = None,
        project_key: str | None = None,
        standing: ProjectStanding | None = None,
        locator_hash: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ReferenceItem]:
        query = select(ReferenceItem).where(ReferenceItem.removed_at.is_(None))
        if character_id is not None or aspect is not None or outfit_id is not None:
            links = select(ReferenceCharacter.reference_id)
            if character_id is not None:
                links = links.where(ReferenceCharacter.character_id == character_id)
            if aspect is not None:
                links = links.where(ReferenceCharacter.aspect == aspect)
            if outfit_id is not None:
                links = links.where(ReferenceCharacter.outfit_id == outfit_id)
            query = query.where(ReferenceItem.id.in_(links))
        if visual_mode_id is not None or facet is not None:
            techniques = select(ReferenceTechnique.reference_id)
            if visual_mode_id is not None:
                techniques = techniques.where(ReferenceTechnique.visual_mode_id == visual_mode_id)
            if facet is not None:
                techniques = techniques.where(ReferenceTechnique.facet == facet)
            query = query.where(ReferenceItem.id.in_(techniques))
        if use is not None:
            query = query.where(
                ReferenceItem.id.in_(
                    select(ReferenceUseLink.reference_id).where(ReferenceUseLink.use == use)
                )
            )
        if reference_class is not None:
            query = query.where(ReferenceItem.reference_class == reference_class)
        if origin is not None:
            query = query.where(ReferenceItem.origin == origin)
        if project_key is not None or standing is not None:
            standings = select(ProjectReferenceStanding.reference_id)
            if project_key is not None:
                standings = standings.where(ProjectReferenceStanding.project_key == project_key)
            if standing is not None:
                standings = standings.where(ProjectReferenceStanding.standing == standing)
            query = query.where(ReferenceItem.id.in_(standings))
        if locator_hash is not None:
            if not is_sha256_hex(locator_hash):
                raise CatalogInputError("A content hash is 64 lowercase hex characters.")
            query = query.where(ReferenceItem.locator.like(f"%:sha256:{locator_hash}%"))
        limit = max(1, min(limit, 500))
        return list(
            self.session.execute(
                query.order_by(ReferenceItem.created_at.desc(), ReferenceItem.id.desc())
                .limit(limit)
                .offset(max(0, offset))
            ).scalars()
        )

    # =====================================================================
    # Bytes and navigation
    # =====================================================================
    def unit_bytes(self, item: ReferenceItem) -> bytes:
        """The whole unit's bytes (page or image), never the file it lives in."""
        asset = self.session.get(LibraryAsset, item.asset_id)
        if asset is None:  # pragma: no cover - FK guarantees it
            raise CatalogNotFoundError("The reference's bytes are not recorded.")
        return self.asset_bytes(asset, item.locator)

    def asset_bytes(self, asset: LibraryAsset, locator_text: str) -> bytes:
        from continuum_core import parse_locator

        locator = parse_locator(locator_text) if not locator_text.startswith("gen:") else None
        changed: SourceChangedError | None = None
        for location in self.locations(asset.id):
            if location.root_key == "source_vault" and locator is not None:
                sources = self._require_sources()
                try:
                    return sources.read_unit(
                        location.relative_path,
                        byte_size=location.byte_size,
                        mtime_ns=location.mtime_ns,
                        locator=locator,
                    ).data
                except SourceChangedError as exc:
                    changed = exc
                    continue
                except SourceUnavailableError:
                    continue
            if location.root_key in (LIBRARY_ROOT, GENERATED_ROOT) and self.derived is not None:
                if self.derived.has(location.root_key, asset.content_hash):
                    return self.derived.get_bytes(location.root_key, asset.content_hash)
        if changed is not None:
            # Every recorded copy was checked; the one that exists holds other bytes.
            raise changed
        raise CatalogNotFoundError(
            "The bytes for this reference are not reachable right now.",
            remediation="Check that the Source Vault is connected and the Library scanned.",
        )

    def reference_image(self, reference_id: uuid.UUID, *, crop: bool = True) -> EncodedImage:
        """A browser preview of the reference: its region when it has one."""
        item = self.reference(reference_id, include_removed=True)
        if item.locator.startswith("pdf:"):
            raise CatalogInputError("PDF pages are opened in the viewer, not previewed here.")
        region = _region_of(item) if crop else None
        return preview(self.unit_bytes(item), region)

    def source_position(self, item: ReferenceItem) -> dict[str, Any]:
        """Where to open the original: viewer id plus page (or instant), if still held."""
        from continuum_core import parse_locator

        provenance = item.provenance or {}
        if provenance.get("kind") == "source_frame":
            locator = parse_locator(str(provenance.get("video_locator")))
        elif item.locator.startswith(("zip:", "pdf:", "image:")):
            locator = parse_locator(item.locator)
        else:
            return {"available": False, "reason": "not held media"}
        asset = self.session.execute(
            select(LibraryAsset).where(LibraryAsset.content_hash == locator.sha256)
        ).scalar_one_or_none()
        if asset is None or asset.origin is not AssetOrigin.SOURCE_VAULT or self.sources is None:
            return {"available": False, "reason": "not held media"}
        if locator.medium.value == "zip" and locator.time_ms is not None:
            return self._member_position(locator.sha256, str(locator.entry), locator.time_ms)
        for location in self.locations(asset.id):
            if location.root_key != "source_vault":
                continue
            media_id = self.sources.media_id_for(location.relative_path)
            if media_id is None:
                continue
            page_index: int | None = None
            if locator.entry is not None:
                page_index = self.sources.page_index_of(
                    media_id, location.relative_path, locator.entry
                )
            elif locator.page is not None:
                page_index = locator.page - 1
            return {
                "available": True,
                "media_id": media_id,
                "page_index": page_index,
                "time_ms": locator.time_ms,
                "held_name": provenance.get("held_name"),
            }
        return {"available": False, "reason": "the source is not in the Library right now"}

    def _member_position(self, archive_hash: str, entry: str, time_ms: int) -> dict[str, Any]:
        """Where to watch an instant of a video stored inside an archive."""
        from continuum_core.catalog import EntryStatus, MemberKind
        from continuum_db.models import CatalogEntry, CatalogMember

        found = self.session.execute(
            select(CatalogMember.id, CatalogMember.name)
            .join(CatalogEntry, CatalogEntry.id == CatalogMember.entry_id)
            .where(
                CatalogEntry.content_hash == archive_hash,
                CatalogEntry.status == EntryStatus.CATALOGUED,
                CatalogMember.kind == MemberKind.VIDEO,
                CatalogMember.name == entry,
            )
            .limit(1)
        ).first()
        if found is None:
            return {"available": False, "reason": "the archive is not in the Library right now"}
        return {
            "available": True,
            "media_id": None,
            "member_id": str(found[0]),
            "page_index": None,
            "time_ms": time_ms,
            "held_name": found[1].rsplit("/", 1)[-1],
        }

    # =====================================================================
    # Internals
    # =====================================================================
    def _create_reference(
        self,
        asset: LibraryAsset,
        locator: str,
        unit_index: int | None,
        spec: ReferenceSpec,
        provenance: dict[str, Any],
    ) -> ReferenceItem:
        region = spec.region
        item = ReferenceItem(
            asset_id=asset.id,
            locator=locator,
            unit_index=unit_index,
            region_x=region.x if region else None,
            region_y=region.y if region else None,
            region_width=region.width if region else None,
            region_height=region.height if region else None,
            reference_class=spec.reference_class,
            origin=spec.origin,
            label=clean_text(spec.label, 300, field="Label"),
            notes=clean_text(spec.notes, 8000, field="Notes"),
            source_url=clean_url(spec.source_url),
            creator_handle=clean_handle(spec.creator_handle),
            favorite=spec.favorite,
            provenance=provenance,
        )
        self.session.add(item)
        self.session.flush()
        if spec.uses:
            self.set_uses(item.id, spec.uses)
        for link in spec.characters:
            self.link_character(item.id, link)
        for technique in spec.techniques:
            self.link_technique(item.id, technique)
        for descriptor in spec.descriptors:
            self.add_descriptor(item.id, descriptor)
        for standing in spec.standings:
            self.set_standing(item.id, standing)
        for panel_source in spec.panel_sources:
            self.add_panel_source(item.id, panel_source)
        return item

    def _store_image(self, data: bytes) -> StoredImage:
        """Land an allowed image; HEIC/HEIF as original plus deterministic PNG.

        Everything is validated (format by content, pixel budget) before a
        single byte is written. The original is stored exactly as received.
        """
        if len(data) > MAX_UPLOAD_IMAGE_BYTES:
            raise CatalogInputError("That image is too large (64 MB at most).")
        # Probes first: raises UnsupportedImageError for anything not allowed.
        rendition = working_rendition(data)
        if rendition is None:
            # Decode once in full, so truncated or corrupt bytes behind a valid
            # header are refused now rather than stored and failing later.
            open_image(data)
            return StoredImage(
                self.store_bytes(
                    data,
                    root_key=LIBRARY_ROOT,
                    medium=AssetMedium.IMAGE,
                    origin=AssetOrigin.USER_ADDED,
                )
            )
        original = self.store_bytes(
            data, root_key=LIBRARY_ROOT, medium=AssetMedium.IMAGE, origin=AssetOrigin.USER_ADDED
        )
        working = self.store_bytes(
            rendition.image.data,
            root_key=LIBRARY_ROOT,
            medium=AssetMedium.IMAGE,
            origin=AssetOrigin.USER_ADDED,
        )
        return StoredImage(
            asset=working,
            original=original,
            conversion={
                "original_sha256": original.content_hash,
                "original_format": rendition.original_format,
                "original_bytes": len(data),
                "rendition": "png",
                "rendition_sha256": working.content_hash,
                "converted_with": rendition.converter,
            },
        )

    @staticmethod
    def _image_locator(asset: LibraryAsset) -> str:
        return f"image:sha256:{asset.content_hash}"

    def _require_sources(self) -> SourceAccess:
        if self.sources is None:
            raise CatalogInputError("The Source Vault is not configured.")
        return self.sources

    @staticmethod
    def _check_user_origin(origin: ReferenceOrigin) -> None:
        if origin not in USER_DECLARED_ORIGINS:
            raise CatalogInputError(
                "Generated and project-approved references are created by production.",
                technical_detail=origin.value,
            )

    @staticmethod
    def _check_version(current: int, expected: int) -> None:
        if current != expected:
            raise CatalogConflictError(
                "This record changed since you loaded it.",
                remediation="Reload and apply your change again.",
            )

    def _flush(self) -> None:
        try:
            self.session.flush()
        except StaleDataError:
            raise CatalogConflictError(
                "This record changed since you loaded it.",
                remediation="Reload and apply your change again.",
            ) from None


def _region_of(item: ReferenceItem | Any) -> NormalizedRegion | None:
    x, y = item.region_x, item.region_y
    width, height = item.region_width, item.region_height
    if x is None or y is None or width is None or height is None:
        return None
    return NormalizedRegion(float(x), float(y), float(width), float(height))


def region_of(item: ReferenceItem | Any) -> NormalizedRegion | None:
    """The normalized region stored on a reference or attempt input, if any."""
    return _region_of(item)


_DOCUMENT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


def _character_origin(
    origin: Any, project_key: str | None, design_documents: Any
) -> tuple[CharacterOrigin, str | None, list[str]]:
    """Validate who designed a character, and where their design lives."""
    try:
        chosen = CharacterOrigin(origin)
    except ValueError:
        raise CatalogInputError(
            "A character is either from a source work or original to a project."
        ) from None
    documents = [str(d) for d in (design_documents or [])]
    if len(documents) > 20 or not all(_DOCUMENT_ID.match(d) for d in documents):
        raise CatalogInputError("Design documents are named by project document id.")
    if chosen is CharacterOrigin.PROJECT_ORIGINAL:
        if not project_key:
            raise CatalogInputError("An original character belongs to a project.")
        require_project_key(project_key)
        return chosen, project_key, documents
    if documents:
        raise CatalogInputError(
            "Design documents define an original character; a source-work character is "
            "defined by its source."
        )
    return chosen, None, []
