"""Phase 1 reference-vault tables, by ADR-0003 tier.

* **Tier A - observed:** ``library_asset`` (bytes, keyed by content hash) and
  ``library_asset_location`` (where those bytes were seen - an observation,
  never identity).
* **Tier B - the user's catalog:** characters, outfits, visual modes,
  reference items and the typed links that say what a reference is for.
* **Tier C - project continuity:** a project's standing for a reference, and
  sources chosen for a specific project page or panel.

Foreign keys point only downward (C -> B -> A); ``tests/invariants`` checks it.

Nothing here stores a Source Vault path as identity or a copy of source
bytes. Removing a catalog row never touches the file it describes: rows are
soft-deleted (``removed_at``) and the source stays exactly where it was.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.catalog import RightsStatus, TrainingEligibility
from continuum_core.references import (
    AssetMedium,
    AssetOrigin,
    CandidateStatus,
    CharacterAspect,
    CharacterOrigin,
    DescriptorFacet,
    DescriptorOrigin,
    IntakeKind,
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
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from continuum_db.models.base import Base, TimestampTz, UuidV7, enum_type

__all__ = [
    "CharacterOutfit",
    "CharacterProfile",
    "IntakeBatch",
    "LibraryAsset",
    "LibraryAssetLocation",
    "OutfitWear",
    "ProjectPanelSource",
    "ProjectReferenceStanding",
    "ProjectVisualModeAssignment",
    "ReferenceCandidate",
    "ReferenceCharacter",
    "ReferenceDescriptor",
    "ReferenceItem",
    "ReferenceTechnique",
    "ReferenceUseLink",
    "VisualMode",
]

#: A normalized region is either entirely absent or entirely present and
#: inside the unit it was selected on.
_REGION_CHECK = (
    "(region_x IS NULL AND region_y IS NULL AND region_width IS NULL AND region_height IS NULL)"
    " OR (region_x >= 0 AND region_y >= 0 AND region_width > 0 AND region_height > 0"
    " AND region_x + region_width <= 1.000001 AND region_y + region_height <= 1.000001)"
)


def _created() -> Mapped[dt.datetime]:
    return mapped_column(TimestampTz, nullable=False, server_default=func.now())


def _updated() -> Mapped[dt.datetime]:
    return mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Tier A - observed bytes
# ---------------------------------------------------------------------------
class LibraryAsset(Base):
    """Bytes Continuum can address, identified only by their content hash."""

    __tablename__ = "library_asset"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    medium: Mapped[AssetMedium] = mapped_column(
        enum_type(AssetMedium, "asset_medium"), nullable=False
    )
    origin: Mapped[AssetOrigin] = mapped_column(
        enum_type(AssetOrigin, "asset_origin"), nullable=False
    )
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_is_sha256"),
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
    )


class LibraryAssetLocation(Base):
    """Where an asset's bytes were observed, and with what size and mtime.

    Resolved only through the storage layer's root-relative containment. The
    size/mtime pair lets a later read detect that the file changed rather
    than silently serving different bytes under the old hash.
    """

    __tablename__ = "library_asset_location"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("library_asset.id", ondelete="RESTRICT"), nullable=False
    )
    root_key: Mapped[str] = mapped_column(String(32), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mtime_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        CheckConstraint(
            "root_key IN ('source_vault', 'library', 'generated')", name="known_root_key"
        ),
        # Defence in depth behind the storage layer's containment: a stored
        # path is forward-slash, relative, and has no '..' segment. Names may
        # legitimately contain dots and colons ("Wait... what", "Title: Sub").
        CheckConstraint(
            r"relative_path <> '' AND relative_path !~ '^/' AND relative_path !~ '^[A-Za-z]:'"
            r" AND position(chr(92) in relative_path) = 0"
            r" AND relative_path !~ '(^|/)\.\.?(/|$)'",
            name="relative_path_is_relative",
        ),
        UniqueConstraint("root_key", "relative_path", "byte_size", "mtime_ns"),
        Index("ix_library_asset_location_asset_id", "asset_id"),
    )


# ---------------------------------------------------------------------------
# Tier B - the user's catalog
# ---------------------------------------------------------------------------
class CharacterProfile(Base):
    """A user-level character identity. Generic: no franchise is known in code."""

    __tablename__ = "character_profile"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_kind: Mapped[SubjectKind] = mapped_column(
        enum_type(SubjectKind, "subject_kind"), nullable=False, default=SubjectKind.CHARACTER
    )
    source_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: SOURCE_WORK (defined by source pages and frames) or PROJECT_ORIGINAL
    #: (defined by one project's own design documents and references).
    origin: Mapped[CharacterOrigin] = mapped_column(
        enum_type(CharacterOrigin, "character_origin"),
        nullable=False,
        default=CharacterOrigin.SOURCE_WORK,
        server_default=CharacterOrigin.SOURCE_WORK.value,
    )
    #: The project an original character belongs to.
    project_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: Ids of that project's documents that define the character's look (a
    #: visual bible). Resolved against the project on every read, never copied.
    design_documents: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scale_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    distinguishing_marks: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posture_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()
    removed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "origin <> 'PROJECT_ORIGINAL' OR project_key IS NOT NULL",
            name="original_character_has_project",
        ),
    )
    __mapper_args__ = {"version_id_col": row_version}


class CharacterOutfit(Base):
    """A wardrobe variant. Belongs to a character; is never its identity.

    ``character_id`` is the garment's *owner*. A different character may wear
    it in a specific project/story state via ``OutfitWear``; borrowing never
    clones the outfit or transfers identity.
    """

    __tablename__ = "character_outfit"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    character_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[OutfitKind] = mapped_column(enum_type(OutfitKind, "outfit_kind"), nullable=False)
    #: Set only for an outfit designed for one project.
    project_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    era: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    season_weather: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    condition: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Human review state for a project-created outfit. Source outfits are not
    #: reviewed (their state is source-faithful, not project-created).
    review_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    #: An optional outfit model sheet / turnaround reference.
    model_sheet_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT"), nullable=True
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()
    removed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint(
            "(kind = 'PROJECT') = (project_key IS NOT NULL)", name="project_outfit_names_project"
        ),
        CheckConstraint(
            "(kind = 'PROJECT') OR (review_status IS NULL)",
            name="only_project_outfits_are_reviewed",
        ),
        CheckConstraint(
            "review_status IS NULL OR review_status IN ('DRAFT', 'REVIEW', 'APPROVED', 'REJECTED')",
            name="outfit_review_status",
        ),
        CheckConstraint(
            "review_status <> 'APPROVED' OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="approved_outfit_has_human",
        ),
        Index("ix_character_outfit_character_id", "character_id"),
    )


class OutfitWear(Base):
    """A garment worn by a character in one project/story state.

    Append-only: a later assignment never rewrites an earlier one, so a
    borrowed garment (e.g. Frieren wearing Mau's hoodie in E14/E18) never
    becomes the owner's or the wearer's default historical outfit. The owner
    is ``outfit.character_id``; ``wearer_character_id`` may differ.
    """

    __tablename__ = "outfit_wear"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    outfit_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_outfit.id", ondelete="RESTRICT"), nullable=False
    )
    wearer_character_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=False
    )
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    #: A semantic stage or episode code: EARLY_ARRIVAL, E14, CASUAL, etc.
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Why this wearer is wearing it here (e.g. "borrowed after reconciliation").
    context: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint("outfit_id", "project_key", "stage"),
        CheckConstraint("stage <> ''", name="outfit_wear_stage_non_empty"),
        Index("ix_outfit_wear_wearer_stage", "wearer_character_id", "project_key", "stage"),
    )


class VisualMode(Base):
    """A named visual language, chosen per project or scene - never per character."""

    __tablename__ = "visual_mode"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[VisualModeCategory] = mapped_column(
        enum_type(VisualModeCategory, "visual_mode_category"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()
    removed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __mapper_args__ = {"version_id_col": row_version}


class ReferenceItem(Base):
    """A catalogued use of one unit of an asset: a page, an image, a region of either.

    ``locator`` is content-derived (ADR-0005) and names the whole unit; a crop
    is the optional region beside it, so the reference always leads back to
    the exact original page. ``unit_index`` is the display position the user
    selected it at - informative only, never used to find the bytes.
    """

    __tablename__ = "reference_item"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("library_asset.id", ondelete="RESTRICT"), nullable=False
    )
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    unit_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_class: Mapped[ReferenceClass] = mapped_column(
        enum_type(ReferenceClass, "reference_class"), nullable=False
    )
    origin: Mapped[ReferenceOrigin] = mapped_column(
        enum_type(ReferenceOrigin, "reference_origin"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Where a user-added reference was found (a post, a gallery). Never fetched.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The named collection a reference was imported with ('' when none).
    collection: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    #: When the material was published where it was found, if known.
    source_posted_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    #: Never assumed: unknown until a person records otherwise.
    rights_status: Mapped[RightsStatus] = mapped_column(
        enum_type(RightsStatus, "rights_status"), nullable=False, default=RightsStatus.UNKNOWN
    )
    #: Never approved by default; model training needs a person's decision.
    training_eligibility: Mapped[TrainingEligibility] = mapped_column(
        enum_type(TrainingEligibility, "training_eligibility"),
        nullable=False,
        default=TrainingEligibility.MANUAL_REVIEW,
    )
    #: Typed provenance union (ADR-0003 section 10), e.g. {"kind": "source", ...}.
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: Who made the image, as a person judged it (PRIMARY_MANGA, OFFICIAL_ANIME,
    #: OFFICIAL_ART, PROJECT_CREATED, FAN_ART, UNKNOWN). ``origin`` and
    #: ``provenance`` keep where it was acquired; this never overwrites them.
    visual_origin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()
    removed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint(_REGION_CHECK, name="region_all_or_none_and_inside"),
        CheckConstraint("unit_index IS NULL OR unit_index >= 0", name="unit_index_non_negative"),
        CheckConstraint(
            "source_url IS NULL OR source_url ~ '^https?://'", name="source_url_is_web"
        ),
        CheckConstraint(
            "visual_origin IS NULL OR visual_origin IN ('PRIMARY_MANGA', 'OFFICIAL_ANIME',"
            " 'OFFICIAL_ART', 'PROJECT_CREATED', 'FAN_ART', 'UNKNOWN')",
            name="visual_origin_known",
        ),
        Index("ix_reference_item_asset_id", "asset_id"),
        Index("ix_reference_item_locator", "locator"),
    )


class ReferenceCharacter(Base):
    """A reference shows this aspect of this character (optionally in this outfit)."""

    __tablename__ = "reference_character"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=False
    )
    outfit_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_outfit.id", ondelete="RESTRICT"), nullable=True
    )
    aspect: Mapped[CharacterAspect] = mapped_column(
        enum_type(CharacterAspect, "character_aspect"), nullable=False
    )
    preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint(
            "reference_id",
            "character_id",
            "aspect",
            "outfit_id",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_reference_character_character_id", "character_id"),
    )


class ReferenceTechnique(Base):
    """A reference helps solve this technique problem (optionally within a visual mode)."""

    __tablename__ = "reference_technique"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="CASCADE"), nullable=False
    )
    visual_mode_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("visual_mode.id", ondelete="RESTRICT"), nullable=True
    )
    facet: Mapped[TechniqueFacet] = mapped_column(
        enum_type(TechniqueFacet, "technique_facet"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint(
            "reference_id", "visual_mode_id", "facet", postgresql_nulls_not_distinct=True
        ),
        Index("ix_reference_technique_visual_mode_id", "visual_mode_id"),
    )


class ReferenceDescriptor(Base):
    """A searchable description. Who asserted it is part of the row."""

    __tablename__ = "reference_descriptor"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="CASCADE"), nullable=False
    )
    facet: Mapped[DescriptorFacet] = mapped_column(
        enum_type(DescriptorFacet, "descriptor_facet"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(200), nullable=False)
    origin: Mapped[DescriptorOrigin] = mapped_column(
        enum_type(DescriptorOrigin, "descriptor_origin"), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    analyzer_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        CheckConstraint(
            "(origin = 'USER' AND confidence IS NULL AND analyzer_ref IS NULL)"
            " OR (origin = 'ANALYSIS' AND analyzer_ref IS NOT NULL"
            " AND (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)))",
            name="origin_matches_evidence",
        ),
        UniqueConstraint("reference_id", "facet", "value", "origin"),
    )


class ReferenceUseLink(Base):
    """What a reference is intended for. The same page may serve several uses."""

    __tablename__ = "reference_use"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="CASCADE"), nullable=False
    )
    use: Mapped[ReferenceUse] = mapped_column(
        enum_type(ReferenceUse, "reference_use_kind"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (UniqueConstraint("reference_id", "use"),)


class IntakeBatch(Base):
    """One intake session in the inbox: a paste of links, a folder of images."""

    __tablename__ = "intake_batch"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    kind: Mapped[IntakeKind] = mapped_column(enum_type(IntakeKind, "intake_kind"), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()


class ReferenceCandidate(Base):
    """A reference waiting to be triaged. Accepting it creates a reference item.

    A URL candidate is a link and nothing more: Continuum never downloads it.
    It becomes acceptable once the user attaches bytes (an image or a
    screenshot), which is when it gains a content-derived locator.
    """

    __tablename__ = "reference_candidate"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("intake_batch.id", ondelete="SET NULL"), nullable=True
    )
    intake_kind: Mapped[IntakeKind] = mapped_column(
        enum_type(IntakeKind, "intake_kind"), nullable=False
    )
    status: Mapped[CandidateStatus] = mapped_column(
        enum_type(CandidateStatus, "candidate_status"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    collection: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    source_posted_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    rights_status: Mapped[RightsStatus] = mapped_column(
        enum_type(RightsStatus, "rights_status"), nullable=False, default=RightsStatus.UNKNOWN
    )
    training_eligibility: Mapped[TrainingEligibility] = mapped_column(
        enum_type(TrainingEligibility, "training_eligibility"),
        nullable=False,
        default=TrainingEligibility.MANUAL_REVIEW,
    )
    #: A display name from the upload, sanitised; never used to find bytes.
    display_name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("library_asset.id", ondelete="RESTRICT"), nullable=True
    )
    #: Where a screenshot was captured from, e.g. a held video's locator and instant.
    capture: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    origin: Mapped[ReferenceOrigin] = mapped_column(
        enum_type(ReferenceOrigin, "reference_origin"), nullable=False
    )
    suggested_class: Mapped[ReferenceClass | None] = mapped_column(
        enum_type(ReferenceClass, "reference_class"), nullable=True
    )
    intended_uses: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="SET NULL"), nullable=True
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint(
            "source_url IS NULL OR source_url ~ '^https?://'", name="source_url_is_web"
        ),
        CheckConstraint(
            "intake_kind <> 'URL' OR source_url IS NOT NULL", name="url_intake_has_url"
        ),
        CheckConstraint(
            "intake_kind NOT IN ('IMAGE', 'VIDEO', 'SCREENSHOT') OR asset_id IS NOT NULL",
            name="file_intake_has_bytes",
        ),
        CheckConstraint(
            "status <> 'ACCEPTED' OR reference_id IS NOT NULL", name="accepted_has_reference"
        ),
        Index("ix_reference_candidate_status", "status"),
        Index("ix_reference_candidate_batch_id", "batch_id"),
    )


# ---------------------------------------------------------------------------
# Tier C - project continuity
# ---------------------------------------------------------------------------
class ProjectReferenceStanding(Base):
    """What a project decided about a library reference. The library is unchanged."""

    __tablename__ = "project_reference_standing"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    #: The project's manifest id; projects are manifests, not rows.
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=True
    )
    standing: Mapped[ProjectStanding] = mapped_column(
        enum_type(ProjectStanding, "project_standing"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint(
            "project_key",
            "reference_id",
            "character_id",
            "standing",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_project_reference_standing_project_key", "project_key"),
    )


class ProjectPanelSource(Base):
    """A reference chosen as source material for one project page or panel."""

    __tablename__ = "project_panel_source"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    episode: Mapped[str] = mapped_column(String(40), nullable=False)
    chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    panel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[PanelSourceRole] = mapped_column(
        enum_type(PanelSourceRole, "panel_source_role"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        CheckConstraint("page >= 1 AND (panel IS NULL OR panel >= 1)", name="page_panel_positive"),
        CheckConstraint("chapter IS NULL OR chapter >= 1", name="chapter_positive"),
        UniqueConstraint(
            "project_key",
            "episode",
            "page",
            "panel",
            "reference_id",
            "role",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_project_panel_source_target", "project_key", "episode", "page"),
    )


class ProjectVisualModeAssignment(Base):
    """A project applies a visual mode to a scope - never globally to a character.

    ``character_id`` names who the mode acts on within the scope: the character
    whose controllable deformed form this is, or who compresses in a comedic
    beat. The character's identity is untouched: the mode is how the moment is
    drawn, not who the character is.
    """

    __tablename__ = "project_visual_mode_assignment"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    visual_mode_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("visual_mode.id", ondelete="RESTRICT"), nullable=False
    )
    scope: Mapped[ModeScope] = mapped_column(enum_type(ModeScope, "mode_scope"), nullable=False)
    episode: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scene: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    panel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trigger: Mapped[ModeTrigger] = mapped_column(
        enum_type(ModeTrigger, "mode_trigger"), nullable=False
    )
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        CheckConstraint(
            "(scope = 'EPISODE' AND episode IS NOT NULL)"
            " OR (scope = 'SCENE' AND episode IS NOT NULL AND scene IS NOT NULL)"
            " OR (scope = 'SEQUENCE' AND episode IS NOT NULL AND page_from IS NOT NULL"
            " AND page_to IS NOT NULL AND page_to >= page_from)"
            " OR (scope = 'PANEL' AND episode IS NOT NULL AND page_from IS NOT NULL"
            " AND panel IS NOT NULL)"
            " OR (scope = 'EVENT' AND event_label IS NOT NULL)",
            name="scope_has_its_target",
        ),
        CheckConstraint(
            "trigger <> 'CHARACTER_CONTROLLED' OR character_id IS NOT NULL",
            name="controlled_has_character",
        ),
        CheckConstraint(
            "(scene IS NULL OR scene >= 1) AND (page_from IS NULL OR page_from >= 1)"
            " AND (panel IS NULL OR panel >= 1)",
            name="positions_positive",
        ),
        Index("ix_project_visual_mode_assignment_project_key", "project_key"),
    )
