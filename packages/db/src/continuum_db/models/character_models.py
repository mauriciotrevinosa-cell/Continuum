"""Project-scoped, versioned character production models and their evidence."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.corpus import (
    ModelSheetKind,
    ModelSheetStatus,
    ProductionEvidenceRole,
    ProductionModelStatus,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from continuum_db.models.base import Base, TimestampTz, UuidV7

__all__ = [
    "CharacterModelSheetAttempt",
    "CharacterProductionEvidence",
    "CharacterProductionModel",
]


def _values(enum: type[Any]) -> str:
    return ", ".join(repr(item.value) for item in enum)


class CharacterProductionModel(Base):
    __tablename__ = "character_production_model"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    character_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default=ProductionModelStatus.DRAFT.value
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    identity_rules: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    restrictions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    active_outfit_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_outfit.id", ondelete="RESTRICT"), nullable=True
    )
    head_sheet_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT"), nullable=True
    )
    body_sheet_reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT"), nullable=True
    )
    created_from: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    approved_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        UniqueConstraint("project_key", "character_id", "version"),
        CheckConstraint(
            f"status IN ({_values(ProductionModelStatus)})", name="production_model_status"
        ),
        CheckConstraint("version > 0", name="production_model_version_positive"),
        CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name="approved_model_has_human",
        ),
        Index("ix_character_production_model_active", "project_key", "character_id", "status"),
        Index(
            "uq_character_production_model_approved",
            "project_key",
            "character_id",
            unique=True,
            postgresql_where=text("status = 'APPROVED'"),
        ),
    )


class CharacterProductionEvidence(Base):
    __tablename__ = "character_production_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_production_model.id", ondelete="CASCADE"), nullable=False
    )
    observation_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_observation.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("model_id", "observation_id", "role"),
        CheckConstraint(
            f"role IN ({_values(ProductionEvidenceRole)})", name="production_evidence_role"
        ),
        CheckConstraint("position >= 0", name="evidence_position_non_negative"),
        Index("ix_character_production_evidence_model", "model_id", "position"),
    )


class CharacterModelSheetAttempt(Base):
    """A provider-backed standardized sheet candidate and its human review state."""

    __tablename__ = "character_model_sheet_attempt"
    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    model_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_production_model.id", ondelete="RESTRICT"), nullable=False
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=False
    )
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    sheet_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Which one of this kind: the outfit, the prop, the look. Empty for kinds
    #: a character only has one of, so the approved-uniqueness rule is the same
    #: expression for every kind.
    variant_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_model_sheet_attempt.id", ondelete="RESTRICT")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    views: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    reference_pack: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT")
    )
    content_hash: Mapped[str | None] = mapped_column(String(64))
    mime: Mapped[str | None] = mapped_column(String(40))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    review_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    generated_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz)

    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "sheet_kind",
            "variant_key",
            "attempt",
            # Named explicitly: the convention name would not fit in 63 characters.
            name="uq_character_model_sheet_attempt_variant_attempt",
        ),
        CheckConstraint(f"sheet_kind IN ({_values(ModelSheetKind)})", name="model_sheet_kind"),
        CheckConstraint(f"status IN ({_values(ModelSheetStatus)})", name="model_sheet_status"),
        CheckConstraint("attempt > 0", name="model_sheet_attempt_positive"),
        CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="model_sheet_hash"
        ),
        CheckConstraint(
            "(status = 'QUEUED') = (content_hash IS NULL)", name="sheet_output_iff_rendered"
        ),
        CheckConstraint(
            "(status IN ('APPROVED', 'REJECTED', 'SUPERSEDED')) = "
            "(reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL)",
            name="sheet_terminal_has_human",
        ),
        Index("ix_character_model_sheet_model", "model_id", "sheet_kind", "attempt"),
        Index(
            "uq_character_model_sheet_approved",
            "project_key",
            "character_id",
            "sheet_kind",
            "variant_key",
            unique=True,
            postgresql_where=text("status = 'APPROVED'"),
        ),
    )
