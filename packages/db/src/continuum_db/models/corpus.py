"""The character reference corpus (M3): observations of a character, by authority.

``character_observation`` (Tier B) holds one observation of one character:
a curated reference, a page of the catalogued source manga, labelled fan art,
or an approved project page. Each row says what it teaches (facets, angle,
expression, pose, framing), how authoritative it is, whether a person has
confirmed it, and how it was found. Rows found automatically start as
CANDIDATE and never ground production until confirmed.

The ``locator`` is the observation's identity for its character:
``ref:<reference id>`` for a reference, ``unit:<catalog unit key>:<page offset>``
for a source page - the same page observed for two characters shares the
locator, which is how co-occurrence (relative scale) is found.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.corpus import (
    Framing,
    ObservationAuthority,
    ObservationRole,
    ObservationSource,
    ObservationStatus,
    ViewAngle,
)
from sqlalchemy import (
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

from continuum_db.models.base import Base, TimestampTz, UuidV7

__all__ = ["CharacterObservation"]


def _in(column: str, values: type[Any]) -> str:
    return f"{column} IN ({', '.join(repr(v.value) for v in values)})"


class CharacterObservation(Base):
    __tablename__ = "character_observation"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    character_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("character_profile.id", ondelete="RESTRICT"), nullable=False
    )
    locator: Mapped[str] = mapped_column(String(200), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("reference_item.id", ondelete="RESTRICT"), nullable=True
    )
    #: The catalog unit's stable key, not its row id: a rescan may rebuild units.
    unit_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    series_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    #: Where in the source it sits, for diversity and for people (a chapter label).
    source_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    authority: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    #: A small curated subset a person prefers for production. Corpus != preferred.
    anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Extreme perspective, comedic deformation, action distortion, shorthand:
    #: kept as evidence, never allowed to redefine the character.
    atypical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    facets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    angle: Mapped[str | None] = mapped_column(String(24), nullable=True)
    framing: Mapped[str | None] = mapped_column(String(12), nullable=True)
    expression: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    pose: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    #: How it was found and any automatic hints: {"discovered_by", "framing_hint", ...}.
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Set when a person reviews it; automatic refreshes never overwrite a review.
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("character_id", "locator"),
        CheckConstraint(_in("source_kind", ObservationSource), name="observation_source"),
        CheckConstraint(_in("authority", ObservationAuthority), name="observation_authority"),
        CheckConstraint(_in("status", ObservationStatus), name="observation_status"),
        CheckConstraint(_in("role", ObservationRole), name="observation_role"),
        CheckConstraint("angle IS NULL OR " + _in("angle", ViewAngle), name="observation_angle"),
        CheckConstraint(
            "framing IS NULL OR " + _in("framing", Framing), name="observation_framing"
        ),
        CheckConstraint(
            "(source_kind = 'SOURCE_PAGE') = (unit_key IS NOT NULL AND page_offset IS NOT NULL)",
            name="source_page_has_unit",
        ),
        CheckConstraint(
            "source_kind = 'SOURCE_PAGE' OR reference_id IS NOT NULL",
            name="reference_observation_has_reference",
        ),
        CheckConstraint("status <> 'CANDIDATE' OR NOT anchor", name="candidates_are_never_anchors"),
        Index("ix_character_observation_locator", "locator"),
    )
