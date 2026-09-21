"""The paid-generation budget: a hard cap, held by reservations.

A budget that is only checked in the user interface is not a budget. These two
tables are the ledger the cap is enforced from:

* every paid request **reserves** its estimated cost before the provider is
  called, inside the transaction that locks the budget row, so two concurrent
  requests cannot both fit in the last dollar;
* a reservation is later **settled** with the real cost, or **released** if the
  request failed or was cancelled. Reserved money is spent money until one of
  those happens;
* amounts are integer micro-dollars, and the database refuses a negative one.

Nothing here decides *whether* paid generation is allowed - that is the
provider policy. This is only what it costs and what is left.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from sqlalchemy import (
    BigInteger,
    Boolean,
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

__all__ = ["SpendBudget", "SpendEntry"]

#: A reservation's life. Only these three states exist.
SPEND_STATES = ("RESERVED", "SETTLED", "RELEASED")


class SpendBudget(Base):
    """One spending cap, for one scope (a project, or the installation)."""

    __tablename__ = "spend_budget"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    scope_key: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    limit_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": row_version}
    __table_args__ = (
        UniqueConstraint("scope_key"),
        CheckConstraint("limit_micros >= 0", name="budget_limit_non_negative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="budget_currency_code"),
    )


class SpendEntry(Base):
    """One reservation against a budget, and what it finally cost."""

    __tablename__ = "spend_entry"

    id: Mapped[uuid.UUID] = mapped_column(UuidV7(), primary_key=True, default=uuid7)
    budget_id: Mapped[uuid.UUID] = mapped_column(
        UuidV7(), ForeignKey("spend_budget.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="RESERVED")
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    #: What the money was for, in Continuum's own words (a character sheet, a
    #: calibration rerun, a panel stage). Never a vendor's endpoint name.
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    images: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    batch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estimated_micros: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actual_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UuidV7(), ForeignKey("job.id", ondelete="SET NULL"), nullable=True
    )
    #: What the spend belongs to in Continuum: an attempt id, a CAL id, a batch item.
    subject: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        TimestampTz, nullable=False, server_default=func.now()
    )
    settled_at: Mapped[dt.datetime | None] = mapped_column(TimestampTz, nullable=True)

    __table_args__ = (
        CheckConstraint("state IN ('RESERVED', 'SETTLED', 'RELEASED')", name="spend_entry_state"),
        CheckConstraint("estimated_micros >= 0", name="spend_estimate_non_negative"),
        CheckConstraint(
            "actual_micros IS NULL OR actual_micros >= 0", name="spend_actual_non_negative"
        ),
        CheckConstraint("images > 0", name="spend_images_positive"),
        CheckConstraint(
            "(state = 'SETTLED') = (actual_micros IS NOT NULL AND settled_at IS NOT NULL)",
            name="settled_entry_has_actual_cost",
        ),
        Index("ix_spend_entry_budget_state", "budget_id", "state"),
        Index("ix_spend_entry_subject", "subject"),
    )
