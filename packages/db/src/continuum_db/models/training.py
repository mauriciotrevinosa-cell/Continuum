"""Training datasets and training runs (M3).

Training is the one place where "it was in the library" must never be enough.
A dataset here is an **exact, hashed manifest**: every item names where it came
from, what it is allowed to be used for, how it was preprocessed and which
split it is in. A dataset is locked before it can be trained on, and a locked
dataset cannot change - a second version is a second row.

Style and structure never share a dataset: a pose or lineart annotation set
teaches a control model, not a look, and mixing them is how a style LoRA
quietly becomes a pose model. The kind is part of the identity of the dataset.

Nothing is trained by these tables. They make a training run reproducible and
inspectable; running it is a separate, deliberate act outside Continuum.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
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

from continuum_db.models.base import Base, TimestampTz, UuidV7

__all__ = ["TrainingDataset", "TrainingDatasetItem", "TrainingRun"]

_SHA256 = "~ '^[0-9a-f]{64}$'"
#: What a dataset teaches. Kept apart on purpose.
DATASET_KINDS = ("STYLE", "STRUCTURE", "SUBJECT")
DATASET_STATES = ("DRAFT", "LOCKED", "RETIRED")
ITEM_SOURCES = ("REFERENCE", "EXTERNAL_RESOURCE")
SPLITS = ("TRAIN", "VALIDATION")
RUN_STATES = ("PLANNED", "PREPARED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED")


class TrainingDataset(Base):
    """One version of one curated training manifest."""

    __tablename__ = "training_dataset"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_key: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="DRAFT")
    #: Deterministic preprocessing: crop policy, target edge, caption template,
    #: deduplication method. Part of what makes the dataset reproducible.
    recipe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: {"validation": 0.1, "seed": 17012026}
    split: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: What the project wants this dataset to teach, as purpose tags. Never a
    #: franchise name: the engine works from tags, the project supplies them.
    purpose_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    manifest_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        UniqueConstraint("project_key", "dataset_key", "version"),
        CheckConstraint("version > 0", name="dataset_version_positive"),
        CheckConstraint("kind IN ('STYLE', 'STRUCTURE', 'SUBJECT')", name="training_dataset_kind"),
        CheckConstraint("state IN ('DRAFT', 'LOCKED', 'RETIRED')", name="training_dataset_state"),
        CheckConstraint(f"manifest_hash IS NULL OR manifest_hash {_SHA256}", name="dataset_hash"),
        # A locked dataset is a fixed manifest, approved by a person.
        CheckConstraint(
            "(state = 'DRAFT') = (manifest_hash IS NULL AND locked_at IS NULL "
            "AND locked_by IS NULL)",
            name="locked_dataset_is_hashed_and_human",
        ),
        Index("ix_training_dataset_project", "project_key", "dataset_key", "version"),
    )


class TrainingDatasetItem(Base):
    """One image in a dataset, with the rights it was admitted under."""

    __tablename__ = "training_dataset_item"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("training_dataset.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT"), nullable=True
    )
    external_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("external_resource.id", ondelete="RESTRICT"), nullable=True
    )
    #: Where the bytes are, in Continuum's locator vocabulary. Never a raw path.
    locator: Mapped[str] = mapped_column(String(500), nullable=False)
    #: The crop taken from that locator, when the item is a panel of a page.
    crop: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    item_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caption: Mapped[str] = mapped_column(Text, nullable=False, default="")
    purpose_tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    split: Mapped[str] = mapped_column(String(12), nullable=False, default="TRAIN")
    #: Snapshot of the rights decision at admission; a later change does not
    #: silently rewrite what a trained model was built from.
    rights_status: Mapped[str] = mapped_column(String(24), nullable=False)
    training_eligibility: Mapped[str] = mapped_column(String(24), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("dataset_id", "item_key"),
        CheckConstraint(
            "source_kind IN ('REFERENCE', 'EXTERNAL_RESOURCE')", name="dataset_item_source"
        ),
        CheckConstraint("split IN ('TRAIN', 'VALIDATION')", name="dataset_item_split"),
        CheckConstraint(f"item_key {_SHA256}", name="dataset_item_key_is_sha256"),
        CheckConstraint(
            f"content_hash IS NULL OR content_hash {_SHA256}", name="dataset_item_hash"
        ),
        CheckConstraint(
            "(source_kind = 'REFERENCE') = (reference_id IS NOT NULL)",
            name="dataset_item_names_its_source",
        ),
        Index("ix_training_dataset_item_dataset", "dataset_id", "split", "position"),
    )


class TrainingRun(Base):
    """One training attempt over one locked dataset, and what it produced."""

    __tablename__ = "training_run"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("training_dataset.id", ondelete="RESTRICT"), nullable=False
    )
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: The base model this adapter is trained on, as the registry names it.
    base_model_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="LORA")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(12), nullable=False, default="PLANNED")
    #: What came out: file name, sha256, license, where it was trained.
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint(
            "state IN ('PLANNED', 'PREPARED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="training_run_state",
        ),
        CheckConstraint(f"config_hash {_SHA256}", name="training_config_hash"),
        Index("ix_training_run_dataset", "dataset_id", "created_at"),
    )
