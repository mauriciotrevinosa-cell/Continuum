"""M3 manga production: materialized chapters, production runs, pages, continuity.

Built on the M2 rough tables rather than beside them: a production page is a
``rough_artifact`` (its attempts, bundle, derivatives and reviews are the M2
rows), and the tables here add what page-by-page production needs.

* ``materialized_chapter`` (Tier C) - the executable chapter computed from the
  committed project documents and placement decisions; stored once per content
  hash.
* ``production_profile`` (Tier C) - how pages are made (backend, models,
  workflow, reference and continuity policy, derivative settings); versioned.
  A PROMOTED profile is the frozen result of a passed sample.
* ``production_run`` (Tier D) - one sample chapter or one canonical production
  run, with its purpose, profile and review decision.
* ``production_page`` (Tier D) - a page of a run in reading order, its state,
  the attempt a person approved, and why it is blocked or stale.
* ``continuity_state`` (Tier D) - the run's continuity context, versioned: a
  new version every time an approved page adds to it.
* ``page_dependency`` (Tier D) - what a page was built from, by version hash,
  so a change upstream marks exactly the dependent pages stale.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.references import RoughPurpose
from sqlalchemy import (
    CheckConstraint,
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
    "ContinuityState",
    "MaterializedChapter",
    "PageDependency",
    "ProductionPage",
    "ProductionProfile",
    "ProductionRun",
]


def _created() -> Mapped[dt.datetime]:
    return mapped_column(TimestampTz, nullable=False, server_default=func.now())


class MaterializedChapter(Base):
    __tablename__ = "materialized_chapter"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    episode: Mapped[str] = mapped_column(String(40), nullable=False)
    chapter: Mapped[int] = mapped_column(Integer, nullable=False)
    materializer_version: Mapped[str] = mapped_column(String(60), nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint("project_key", "episode", "chapter", "body_hash"),
        CheckConstraint("chapter >= 1", name="chapter_positive"),
        CheckConstraint("body_hash ~ '^[0-9a-f]{64}$'", name="body_hash_is_sha256"),
    )


class ProductionProfile(Base):
    __tablename__ = "production_profile"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: DRAFT (editable in spirit; every change is a new version), PROMOTED
    #: (frozen by a passed sample), RETIRED.
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    #: The sample run whose pass promoted it. Not a foreign key: a project-tier
    #: row never points into the generated tier (ADR-0003).
    promoted_from_run: Mapped[uuid.UUID | None] = mapped_column(UuidV7(), nullable=True)
    promoted_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint("project_key", "name", "version"),
        CheckConstraint("status IN ('DRAFT', 'PROMOTED', 'RETIRED')", name="profile_status"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "(status = 'PROMOTED') = (promoted_at IS NOT NULL)", name="promoted_iff_dated"
        ),
    )


class ProductionRun(Base):
    __tablename__ = "production_run"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    episode: Mapped[str] = mapped_column(String(40), nullable=False)
    #: A sample covers one chapter; a canonical run may cover the whole episode.
    chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    purpose: Mapped[RoughPurpose] = mapped_column(
        enum_type(RoughPurpose, "rough_purpose"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("production_profile.id", ondelete="RESTRICT"), nullable=False
    )
    #: OPEN, SAMPLE_PASSED, SAMPLE_FAILED, CLOSED.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    decision_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        CheckConstraint("purpose IN ('PRODUCTION', 'NON_CANON_SAMPLE')", name="run_purpose"),
        CheckConstraint(
            "status IN ('OPEN', 'SAMPLE_PASSED', 'SAMPLE_FAILED', 'CLOSED')", name="run_status"
        ),
        CheckConstraint(
            "status NOT IN ('SAMPLE_PASSED', 'SAMPLE_FAILED') OR purpose = 'NON_CANON_SAMPLE'",
            name="only_samples_pass_or_fail",
        ),
        Index("ix_production_run_project_key", "project_key"),
    )


class ProductionPage(Base):
    __tablename__ = "production_page"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("production_run.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    materialized_chapter_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("materialized_chapter.id", ondelete="RESTRICT"), nullable=False
    )
    page_key: Mapped[str] = mapped_column(String(80), nullable=False)
    page_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("rough_artifact.id", ondelete="RESTRICT"), nullable=False
    )
    #: WAITING (an earlier page is not approved), BLOCKED, READY, IN_REVIEW,
    #: APPROVED, STALE.
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Why it is blocked or stale: [{"kind", "key", "old", "new", "detail"}].
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    approved_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("rough_attempt.id", ondelete="RESTRICT"), nullable=True
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        UniqueConstraint("artifact_id"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint(
            "state IN ('WAITING', 'BLOCKED', 'READY', 'IN_REVIEW', 'APPROVED', 'STALE')",
            name="page_state",
        ),
        CheckConstraint(
            "state <> 'APPROVED' OR approved_attempt_id IS NOT NULL", name="approved_has_attempt"
        ),
    )


class ContinuityState(Base):
    __tablename__ = "continuity_state"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("production_run.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_at: Mapped[dt.datetime] = _created()

    __table_args__ = (
        UniqueConstraint("run_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class PageDependency(Base):
    __tablename__ = "page_dependency"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    page_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("production_page.id", ondelete="RESTRICT"), nullable=False
    )
    #: MATERIALIZED_PAGE, SOURCE_DOCUMENT, CHARACTER_REFERENCES, PROFILE.
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    version_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[dt.datetime] = _created()

    __table_args__ = (UniqueConstraint("page_id", "kind", "key"),)
