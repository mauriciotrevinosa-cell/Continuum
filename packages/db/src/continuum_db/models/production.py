"""Phase 1 rough-manga production tables - ADR-0003 Tier D (generated).

* ``rough_artifact`` - the stable thing a user sees: one project page or panel.
* ``generation_recipe`` - intent and execution, each with its own hash
  (ADR-0005 section 3). The same schema describes generation *and* editing:
  source plates, preserved/removed/replaced regions and every bundle role are
  intent; provider, workflow, seed, masks and settings are execution.
* ``rough_attempt`` - an immutable, numbered attempt. Regenerating creates the
  next number; nothing is overwritten.
* ``attempt_input`` - the reference bundle, **snapshotted**: locator, region
  and role are copied, so removing a catalog record never breaks the chain
  from artifact back to the original source page.
* ``attempt_derivative`` - bytes an attempt produced (output, masks, source
  crops), all content-addressed under ``generated/``.
* ``attempt_review`` - append-only review history.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.references import (
    AttemptState,
    BundleRole,
    CharacterAspect,
    DerivativeKind,
    PanelStage,
    RenderOutput,
    ReviewDecision,
    RoughArtifactKind,
    RoughMode,
    RoughPurpose,
)
from sqlalchemy import (
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
    "AttemptDerivative",
    "AttemptInput",
    "AttemptReview",
    "GenerationRecipe",
    "RoughArtifact",
    "RoughAttempt",
]


class RoughArtifact(Base):
    """One project page or panel in rough form, across all its attempts."""

    __tablename__ = "rough_artifact"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    episode: Mapped[str] = mapped_column(String(40), nullable=False)
    chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    panel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[RoughArtifactKind] = mapped_column(
        enum_type(RoughArtifactKind, "rough_artifact_kind"), nullable=False
    )
    #: PRODUCTION work, a WORKFLOW_TEST or a NON_CANON_SAMPLE. Tests and samples
    #: live beside production pages without ever colliding with or counting as them.
    purpose: Mapped[RoughPurpose] = mapped_column(
        enum_type(RoughPurpose, "rough_purpose"),
        nullable=False,
        default=RoughPurpose.PRODUCTION,
        server_default=RoughPurpose.PRODUCTION.value,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    #: M3: the production run the page belongs to (keeps two sample runs apart).
    production_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("production_run.id", ondelete="RESTRICT"), nullable=True
    )
    #: The approved panel-script document (project manifest id) and version.
    panel_script_document: Mapped[str | None] = mapped_column(String(80), nullable=True)
    panel_script_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    brief: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: M3 layered construction: the construction stage of a panel this artifact
    #: holds (COMPOSITION ... FINISH). Each stage keeps its own attempts, reviews
    #: and approvals. NULL for a whole page or a single-pass panel.
    stage: Mapped[PanelStage | None] = mapped_column(
        enum_type(PanelStage, "panel_stage"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("page >= 1 AND (panel IS NULL OR panel >= 1)", name="page_panel_positive"),
        CheckConstraint("(kind = 'PANEL') = (panel IS NOT NULL)", name="panel_kind_has_panel"),
        CheckConstraint("chapter IS NULL OR chapter >= 1", name="chapter_positive"),
        CheckConstraint("stage IS NULL OR kind = 'PANEL'", name="stage_is_a_panel_stage"),
        UniqueConstraint(
            "project_key",
            "purpose",
            "production_run_id",
            "episode",
            "page",
            "panel",
            "kind",
            "stage",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_rough_artifact_project_key", "project_key"),
    )


class GenerationRecipe(Base):
    """What an attempt was asked to be (intent) and how it was made (execution)."""

    __tablename__ = "generation_recipe"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    mode: Mapped[RoughMode] = mapped_column(enum_type(RoughMode, "rough_mode"), nullable=False)
    recipe_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    template_package_version: Mapped[str] = mapped_column(String(40), nullable=False)
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    execution: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    intent_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("intent_hash ~ '^[0-9a-f]{64}$'", name="intent_hash_is_sha256"),
        CheckConstraint("execution_hash ~ '^[0-9a-f]{64}$'", name="execution_hash_is_sha256"),
        Index("ix_generation_recipe_intent_hash", "intent_hash"),
    )


class RoughAttempt(Base):
    """An immutable attempt. Only its review state ever changes."""

    __tablename__ = "rough_attempt"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    artifact_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("rough_artifact.id", ondelete="RESTRICT"), nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("generation_recipe.id", ondelete="RESTRICT"), nullable=False
    )
    parent_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("rough_attempt.id", ondelete="RESTRICT"), nullable=True
    )
    #: The durable job that renders it. Job rows are operational history and
    #: may be pruned; the attempt and its bytes are not.
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="SET NULL"), nullable=True
    )
    state: Mapped[AttemptState] = mapped_column(
        enum_type(AttemptState, "attempt_state"), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: What the image is evidence of, set by the renderer that drew it.
    output_class: Mapped[RenderOutput | None] = mapped_column(
        enum_type(RenderOutput, "render_output"), nullable=True
    )
    #: M3: the production page, continuity version and profile it was made for.
    production_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("production_page.id", ondelete="RESTRICT"), nullable=True
    )
    continuity_state_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("continuity_state.id", ondelete="RESTRICT"), nullable=True
    )
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("production_profile.id", ondelete="RESTRICT"), nullable=True
    )
    #: Exact backend, model/checkpoint (name, version, sha256, license, source),
    #: workflow (id, version, sha256) and settings. Required for artwork.
    artwork_provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    mime: Mapped[str | None] = mapped_column(String(40), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    generated_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __table_args__ = (
        UniqueConstraint("artifact_id", "attempt"),
        CheckConstraint("attempt >= 1", name="attempt_positive"),
        CheckConstraint("(state = 'QUEUED') = (content_hash IS NULL)", name="output_iff_rendered"),
        CheckConstraint(
            "(state = 'QUEUED') = (output_class IS NULL)", name="output_class_iff_rendered"
        ),
        CheckConstraint(
            "state NOT IN ('CREATIVE_APPROVED', 'FINAL_APPROVED')"
            " OR output_class = 'ARTWORK_CANDIDATE'",
            name="creative_approval_needs_artwork",
        ),
        CheckConstraint(
            "output_class IS DISTINCT FROM 'ARTWORK_CANDIDATE' OR (artwork_provenance ? 'model'"
            " AND artwork_provenance ? 'workflow' AND artwork_provenance ? 'settings'"
            " AND artwork_provenance ? 'backend')",
            name="artwork_is_reproducible",
        ),
        CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_is_sha256"
        ),
        Index("ix_rough_attempt_job_id", "job_id"),
    )


class AttemptInput(Base):
    """One member of an attempt's reference bundle, snapshotted for provenance."""

    __tablename__ = "attempt_input"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("rough_attempt.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[BundleRole] = mapped_column(enum_type(BundleRole, "bundle_role"), nullable=False)
    #: The catalog record it was chosen from, when it still exists.
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="SET NULL"), nullable=True
    )
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    unit_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    region_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    region_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="SET NULL"), nullable=True
    )
    outfit_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_outfit.id", ondelete="SET NULL"), nullable=True
    )
    aspect: Mapped[CharacterAspect | None] = mapped_column(
        enum_type(CharacterAspect, "character_aspect"), nullable=True
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    #: The reference's provenance at the moment it was chosen: origin, class,
    #: collection, creator, rights, training eligibility, asset hash and the
    #: catalog's own provenance record. Later edits to the catalog never change
    #: what this attempt was given.
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    __table_args__ = (
        UniqueConstraint("attempt_id", "position"),
        CheckConstraint(
            "(region_x IS NULL AND region_y IS NULL AND region_width IS NULL"
            " AND region_height IS NULL) OR (region_x >= 0 AND region_y >= 0"
            " AND region_width > 0 AND region_height > 0"
            " AND region_x + region_width <= 1.000001 AND region_y + region_height <= 1.000001)",
            name="region_all_or_none_and_inside",
        ),
        Index("ix_attempt_input_locator", "locator"),
        Index("ix_attempt_input_reference_id", "reference_id"),
    )


class AttemptDerivative(Base):
    """Bytes an attempt produced. Masks and crops are artifacts, never edits to source."""

    __tablename__ = "attempt_derivative"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("rough_attempt.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[DerivativeKind] = mapped_column(
        enum_type(DerivativeKind, "derivative_kind"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Which edit operation or input it belongs to, when it belongs to one.
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash_is_sha256"),
        UniqueConstraint("attempt_id", "kind", "content_hash"),
    )


class AttemptReview(Base):
    """An append-only review decision."""

    __tablename__ = "attempt_review"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    attempt_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("rough_attempt.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[ReviewDecision] = mapped_column(
        enum_type(ReviewDecision, "review_decision"), nullable=False
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: When an upgrade changed what a recorded decision means, the decision as
    #: it was originally recorded (e.g. an M2 test-render ``APPROVE``).
    reclassified_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_attempt_review_attempt_id", "attempt_id"),)
