"""Declarative base and shared column types (ADR-0003 section 1).

Two decisions are enforced here rather than left to each model:

* **UUIDv7 primary keys** (D-07) -- time-ordered for index locality and
  globally unique so export/import and cross-machine merges cannot collide.
* **``timestamptz`` everywhere, defaulted by the DATABASE clock** (D-09).
  Lease expiry must not depend on a worker's local clock: skew between two
  machines could otherwise expire a live lease and cause duplicate work.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import TypeDecorator, Uuid

__all__ = ["Base", "JsonDict", "TimestampTz", "db_now", "pk_column", "timestamp_column"]

#: Explicit naming so Alembic autogenerate produces stable, reviewable names
#: instead of database-assigned ones that differ between environments.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

TimestampTz = DateTime(timezone=True)
JsonDict = JSONB


class Base(DeclarativeBase):
    """Base for every Continuum table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        dict[str, Any]: JSONB,
        dt.datetime: TimestampTz,
    }


class UuidV7(TypeDecorator[uuid.UUID]):
    """A UUID column whose Python-side default is a UUIDv7."""

    impl = Uuid(as_uuid=True)
    cache_ok = True


def pk_column() -> Any:
    """Standard UUIDv7 primary key."""
    return mapped_column(UuidV7(), primary_key=True, default=uuid7)


def timestamp_column(*, server_default: bool = False, nullable: bool = True) -> Any:
    """A ``timestamptz`` column, optionally defaulted by the database clock."""
    return mapped_column(
        TimestampTz,
        nullable=nullable,
        server_default=func.now() if server_default else None,
    )


def db_now() -> Any:
    """SQL ``now()`` -- the only clock used for leases and scheduling."""
    return func.now()
