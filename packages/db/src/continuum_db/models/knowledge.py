"""Visual Knowledge: the external-resource registry (M3) - ADR-0003 Tier B.

``external_resource`` records a dataset, annotation set, model or tool that
Continuum may use, as a person decided: its license, whether access was
requested or granted, when its license was accepted locally, which read-only
intake folder holds its bytes, and the ceiling of what material from it may be
used for. The committed registry document proposes; this row is the decision.

Nothing here stores a local path (an intake binding is a root *key*) or any
byte of the resource. The database refuses a training approval without a
recorded license acceptance.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from sqlalchemy import CheckConstraint, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from continuum_db.models.base import Base, TimestampTz, UuidV7

__all__ = ["ExternalResource"]

_KINDS = ("DATASET", "ANNOTATIONS", "MODEL", "TOOL", "RESEARCH", "UNVERIFIED")
_ACCESS = ("OPEN", "NOT_REQUESTED", "REQUESTED", "GRANTED", "DENIED", "UNKNOWN")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ExternalResource(Base):
    __tablename__ = "external_resource"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    #: The registry id, e.g. ``manga109-s-v2026``. Stable across imports.
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    urls: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    license_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    access_state: Mapped[str] = mapped_column(String(20), nullable=False)
    #: When a person accepted the resource's license locally, and on what terms.
    license_accepted_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)
    license_acceptance_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: What the committed registry proposes (KnowledgeUse values). Never training-approved.
    proposed_uses: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: What a person allows - the ceiling for every item from this resource.
    allowed_uses: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    #: The read-only intake root holding its bytes (``intake:...``), never a path.
    intake_root_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: The registry entry as last imported, and its canonical hash.
    registry_entry: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    registry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        CheckConstraint("key ~ '^[a-z0-9][a-z0-9._-]{1,79}$'", name="key_format"),
        CheckConstraint(_in("kind", _KINDS), name="kind_known"),
        CheckConstraint(_in("access_state", _ACCESS), name="access_known"),
        CheckConstraint(
            "intake_root_key IS NULL OR intake_root_key ~ '^intake:[a-z0-9-]{1,57}$'",
            name="intake_root_is_a_key",
        ),
        CheckConstraint(
            "jsonb_typeof(allowed_uses) = 'array' AND jsonb_typeof(proposed_uses) = 'array'",
            name="uses_are_lists",
        ),
        CheckConstraint(
            "NOT (proposed_uses ? 'TRAINING_APPROVED')", name="registry_never_approves_training"
        ),
        CheckConstraint(
            "NOT (allowed_uses ? 'TRAINING_APPROVED') OR (license_accepted_at IS NOT NULL"
            " AND access_state IN ('OPEN', 'GRANTED'))",
            name="training_needs_accepted_license",
        ),
        CheckConstraint("registry_hash ~ '^[0-9a-f]{64}$'", name="registry_hash_is_sha256"),
    )
