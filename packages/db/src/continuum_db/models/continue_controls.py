"""Presentation state for the Studio's Continue shelf.

A dismissal is deliberately separate from :class:`MediaProgress`: hiding a
card must never rewrite or erase reading/watching history.  The durable key is
the same group Continuum already uses for Continue (series when known, unit
otherwise) plus medium, so reading and watching can be controlled
independently.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from continuum_db.models.base import Base, pk_column, timestamp_column

__all__ = ["MediaProgressDismissal"]


class MediaProgressDismissal(Base):
    """A hidden Continue group; fresh activity removes the dismissal."""

    __tablename__ = "media_progress_dismissal"

    id: Mapped[uuid.UUID] = pk_column()
    profile_key: Mapped[str] = mapped_column(String(40), nullable=False)
    project_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    group_key: Mapped[str] = mapped_column(String(120), nullable=False)
    medium: Mapped[str] = mapped_column(String(16), nullable=False)
    hidden_at: Mapped[dt.datetime] = timestamp_column(server_default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("profile_key", "project_key", "group_key", "medium"),
        CheckConstraint("medium IN ('READING', 'WATCHING')", name="medium_valid"),
    )
