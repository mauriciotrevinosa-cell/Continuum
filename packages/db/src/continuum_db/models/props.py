"""Recurring objects a project keeps the same size (M3).

A prop belongs to a project, optionally to a character, and carries its own
measurements and the body part its size is read against. Its references are
linked by what they show (front, profile, detail, worn, beside something of
known size), so a scale plate is never mistaken for a look reference.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.props import PropStatus, PropView, ScaleAnchor
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

__all__ = ["ProjectProp", "ProjectPropReference"]


def _values(enum: type[Any]) -> str:
    return ", ".join(repr(item.value) for item in enum)


class ProjectProp(Base):
    """One object whose size and construction the project keeps stable."""

    __tablename__ = "project_prop"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False)
    prop_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The character it belongs to, when it belongs to one.
    character_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=True
    )
    #: {length_mm, width_mm, height_mm, diameter_mm, approximate}
    size: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: {relative_to: ScaleAnchor, ratio: float}
    body_scale: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Only filled when the object became more than decoration in the story.
    narrative_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=PropStatus.DRAFT.value)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        UniqueConstraint("project_key", "prop_key"),
        CheckConstraint(f"status IN ({_values(PropStatus)})", name="project_prop_status"),
        CheckConstraint("prop_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="project_prop_key_format"),
        CheckConstraint("project_key ~ '^[a-z0-9][a-z0-9-]{0,79}$'", name="prop_project_key"),
        CheckConstraint(
            "(status = 'APPROVED') = (approved_at IS NOT NULL AND approved_by IS NOT NULL)",
            name="approved_prop_has_human",
        ),
        Index("ix_project_prop_character", "project_key", "character_id"),
    )


class ProjectPropReference(Base):
    """One reference image of a prop, by what it shows."""

    __tablename__ = "project_prop_reference"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    prop_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("project_prop.id", ondelete="CASCADE"), nullable=False
    )
    reference_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT"), nullable=False
    )
    view: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("prop_id", "reference_id", "view"),
        CheckConstraint(f"view IN ({_values(PropView)})", name="prop_reference_view"),
        CheckConstraint("position >= 0", name="prop_reference_position"),
        Index("ix_project_prop_reference_prop", "prop_id", "position"),
    )


#: Kept next to the model so a reader sees the vocabulary the column allows.
SCALE_ANCHORS = tuple(anchor.value for anchor in ScaleAnchor)
