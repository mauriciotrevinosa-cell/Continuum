"""Phase 1.5 full-Vault catalog tables, by ADR-0003 tier.

* **Tier A - observed:** ``catalog_scan`` (one pass over one root),
  ``catalog_entry`` (one file: size, mtime, what its bytes are, its hash) and
  ``catalog_member`` (the archive members worth recording: each video, each
  folder of pages). Observations only - nothing here says what a file *means*.
* **Tier B - interpretation:** ``catalog_unit`` (a chapter, an episode, an
  image, with the confidence and evidence behind that reading) and
  ``media_progress`` (how far the user has read or watched a unit).
* **Tier C - project:** ``reference_manifest`` (a deterministic list of
  production inputs), ``chapter_package`` (a chapter's production package)
  and ``music_reference`` (playlist and music notes).

Identity never depends on a row id where it has to survive a rescan: a unit's
``unit_key`` is derived from where it lives, so reading progress attached to
it outlives every re-identification. No column stores source bytes; paths are
root-relative observations, resolved only through the storage layer.
"""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from continuum_core import uuid7
from continuum_core.catalog import (
    ApprovalState,
    Confidence,
    DetectedKind,
    EntryStatus,
    EpisodeKind,
    HashSource,
    MaterialClass,
    MemberKind,
    ProgressMedium,
    ScanStatus,
    UnitKind,
)
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from continuum_db.models.base import Base, TimestampTz, UuidV7, enum_type

__all__ = [
    "CatalogEntry",
    "CatalogMember",
    "CatalogScan",
    "CatalogUnit",
    "ChapterPackage",
    "MediaProgress",
    "MusicReference",
    "ReferenceManifest",
]

_ROOT_KEY_CHECK = "root_key ~ '^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$'"
_RELATIVE_CHECK = (
    r"relative_path <> '' AND relative_path !~ '^/' AND relative_path !~ '^[A-Za-z]:'"
    r" AND position(chr(92) in relative_path) = 0"
    r" AND relative_path !~ '(^|/)\.\.?(/|$)'"
)
_SHA256 = "~ '^[0-9a-f]{64}$'"


def _created() -> Mapped[dt.datetime]:
    return mapped_column(TimestampTz, nullable=False, server_default=func.now())


def _updated() -> Mapped[dt.datetime]:
    return mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------------------
# Tier A - observed
# ---------------------------------------------------------------------------
class CatalogScan(Base):
    """One pass of the catalog over one root, with what it found and skipped."""

    __tablename__ = "catalog_scan"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    root_key: Mapped[str] = mapped_column(String(48), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[ScanStatus] = mapped_column(enum_type(ScanStatus, "scan_status"), nullable=False)
    scanner_version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Files found, directories walked, and every entry deliberately skipped.
    survey: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: new / changed / unchanged / missing / failed / unsupported, set on completion.
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    started_at: Mapped[dt.datetime] = _created()
    finished_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __table_args__ = (
        CheckConstraint(_ROOT_KEY_CHECK, name="root_key_is_catalog_root"),
        Index("ix_catalog_scan_root_key_started_at", "root_key", "started_at"),
    )


class CatalogEntry(Base):
    """One file under a catalog root, as last observed. Never a copy of it."""

    __tablename__ = "catalog_entry"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    root_key: Mapped[str] = mapped_column(String(48), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    extension: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mtime_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_kind: Mapped[DetectedKind] = mapped_column(
        enum_type(DetectedKind, "detected_kind"), nullable=False
    )
    detected_format: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    status: Mapped[EntryStatus] = mapped_column(
        enum_type(EntryStatus, "entry_status"), nullable=False
    )
    #: Why an entry is unsupported or failed, in words a person can act on.
    status_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    material_class: Mapped[MaterialClass] = mapped_column(
        enum_type(MaterialClass, "material_class"), nullable=False
    )
    collection: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    series_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    series_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Facts read from the file or its name (engine metadata, creator, posted_at...).
    facts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: The archive view: pages, bundle, mixed or none. Null for other files.
    archive_view: Mapped[str | None] = mapped_column(String(16), nullable=True)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quick_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash_source: Mapped[HashSource | None] = mapped_column(
        enum_type(HashSource, "hash_source"), nullable=True
    )
    #: The size and mtime the hash was taken at; a hash is trusted only while
    #: the file still has both.
    hashed_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    hashed_mtime_ns: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("catalog_entry.id", ondelete="SET NULL"), nullable=True
    )
    scanner_version: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen_scan_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("catalog_scan.id", ondelete="SET NULL"), nullable=True
    )
    last_seen_at: Mapped[dt.datetime] = _created()
    missing_since: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        UniqueConstraint("root_key", "relative_path"),
        CheckConstraint(_ROOT_KEY_CHECK, name="root_key_is_catalog_root"),
        CheckConstraint(_RELATIVE_CHECK, name="relative_path_is_relative"),
        CheckConstraint(f"content_hash IS NULL OR content_hash {_SHA256}", name="hash_is_sha256"),
        CheckConstraint(
            "content_hash IS NULL OR (hashed_size IS NOT NULL AND hashed_mtime_ns IS NOT NULL"
            " AND hash_source IS NOT NULL)",
            name="hash_records_its_observation",
        ),
        CheckConstraint("byte_size >= 0", name="byte_size_non_negative"),
        Index("ix_catalog_entry_content_hash", "content_hash"),
        Index("ix_catalog_entry_series_key", "series_key"),
        Index("ix_catalog_entry_status", "status"),
    )


class CatalogMember(Base):
    """One recorded member of an archive: a video, or a folder of pages."""

    __tablename__ = "catalog_member"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("catalog_entry.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[MemberKind] = mapped_column(enum_type(MemberKind, "member_kind"), nullable=False)
    #: A video's entry name, or the folder of a page group ('' for the top level).
    name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    compressed_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    crc32: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    compress_type: Mapped[int | None] = mapped_column(Integer, nullable=True)
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: A video extracted on demand into the managed cache, by content hash.
    cached_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cached_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint("entry_id", "kind", "name"),
        CheckConstraint(
            f"cached_sha256 IS NULL OR cached_sha256 {_SHA256}", name="cached_hash_is_sha256"
        ),
        Index("ix_catalog_member_entry_id", "entry_id"),
    )


# ---------------------------------------------------------------------------
# Tier B - interpretation
# ---------------------------------------------------------------------------
class CatalogUnit(Base):
    """A chapter, an episode, an image: what Continuum reads a file or member as."""

    __tablename__ = "catalog_unit"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    #: Derived from the unit's location, so it survives re-identification.
    unit_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("catalog_entry.id", ondelete="CASCADE"), nullable=False
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("catalog_member.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[UnitKind] = mapped_column(enum_type(UnitKind, "unit_kind"), nullable=False)
    material_class: Mapped[MaterialClass] = mapped_column(
        enum_type(MaterialClass, "material_class"), nullable=False
    )
    collection: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    series_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    series_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    program_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_kind: Mapped[EpisodeKind | None] = mapped_column(
        enum_type(EpisodeKind, "episode_kind"), nullable=True
    )
    chapter_number: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    #: Reading order within a series: material, season, number, name.
    sort_key: Mapped[str] = mapped_column(String(400), nullable=False)
    first_page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Confidence] = mapped_column(
        enum_type(Confidence, "confidence"), nullable=False
    )
    evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: Lowercased words searched by the catalog: titles, labels, file name.
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        CheckConstraint("season IS NULL OR season >= 0", name="season_non_negative"),
        CheckConstraint("episode IS NULL OR episode >= 0", name="episode_non_negative"),
        CheckConstraint(
            "first_page_index IS NULL OR first_page_index >= 0", name="first_page_non_negative"
        ),
        Index("ix_catalog_unit_entry_id", "entry_id"),
        Index("ix_catalog_unit_series", "series_key", "kind", "sort_key"),
    )


class MediaProgress(Base):
    """How far a person has read or watched one unit. Survives every rescan."""

    __tablename__ = "media_progress"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    profile_key: Mapped[str] = mapped_column(String(40), nullable=False, default="local")
    #: '' outside a project; progress inside a project is kept apart.
    project_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    unit_key: Mapped[str] = mapped_column(String(64), nullable=False)
    medium: Mapped[ProgressMedium] = mapped_column(
        enum_type(ProgressMedium, "progress_medium"), nullable=False
    )
    series_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Where the unit lives, so progress can be followed back after a rescan.
    root_key: Mapped[str] = mapped_column(String(48), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    member_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    opened_at: Mapped[dt.datetime] = mapped_column(TimestampTz, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    updated_at: Mapped[dt.datetime] = _updated()

    __table_args__ = (
        UniqueConstraint("profile_key", "project_key", "unit_key"),
        CheckConstraint(_ROOT_KEY_CHECK, name="root_key_is_catalog_root"),
        CheckConstraint(_RELATIVE_CHECK, name="relative_path_is_relative"),
        CheckConstraint("page_index IS NULL OR page_index >= 0", name="page_non_negative"),
        CheckConstraint("position_ms IS NULL OR position_ms >= 0", name="position_non_negative"),
        Index("ix_media_progress_recent", "profile_key", "project_key", "opened_at"),
        Index("ix_media_progress_series", "profile_key", "series_key"),
    )


# ---------------------------------------------------------------------------
# Tier C - project
# ---------------------------------------------------------------------------
class ReferenceManifest(Base):
    """A deterministic, hashed list of production inputs, with their provenance."""

    __tablename__ = "reference_manifest"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: What was asked for, as given.
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    #: What it resolved to, in canonical order.
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint("project_key", "manifest_hash"),
        CheckConstraint(f"manifest_hash {_SHA256}", name="manifest_hash_is_sha256"),
        CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="project_key_format"),
    )


class ChapterPackage(Base):
    """One version of a chapter's production package. A new version never overwrites."""

    __tablename__ = "chapter_package"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    package_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    approval_state: Mapped[ApprovalState] = mapped_column(
        enum_type(ApprovalState, "approval_state"), nullable=False
    )
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        UniqueConstraint("project_key", "package_key", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(f"body_hash {_SHA256}", name="body_hash_is_sha256"),
        CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="project_key_format"),
        CheckConstraint("package_key ~ '^[a-z0-9][a-z0-9-]{0,119}$'", name="package_key_format"),
    )


class MusicReference(Base):
    """A track noted for a project: reference metadata only, never fetched or played."""

    __tablename__ = "music_reference"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    track: Mapped[str] = mapped_column(String(300), nullable=False)
    artist: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    #: A link or a free-text pointer (album, playlist position). Never fetched.
    reference: Mapped[str] = mapped_column(Text, nullable=False, default="")
    episode: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    scene: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    mood: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    intended_use: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()
    removed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="project_key_format"),
        Index("ix_music_reference_project_key", "project_key"),
    )
