"""Reading and watching progress that survives restarts and rescans.

Progress is keyed by a unit's *location-derived* key (see
:func:`~continuum_library.vault_catalog.unit_key_for`), not by a catalog row:
rescans rebuild units, re-identify episodes and renumber pages without ever
touching a person's place in a chapter or an episode. A unit the catalog has
not observed yet still gets progress - its key is computed the same way from
the file the viewer opened.

Recorded per unit: the page (manga) or the playback position (video), when it
was last opened, and when it was completed. Series-level "last opened" and
"last completed" are read from those rows; nothing is denormalised.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import uuid7
from continuum_core.catalog import EntryStatus, MemberKind, ProgressMedium, UnitKind
from continuum_db.models import CatalogEntry, CatalogMember, CatalogUnit, MediaProgress
from continuum_storage import MediaLibrary, MediaUnavailableError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from continuum_library.identify import place
from continuum_library.validation import (
    CatalogInputError,
    CatalogNotFoundError,
    require_project_key,
)
from continuum_library.vault_catalog import unit_key_for
from continuum_library.vault_views import PROFILE, unit_view

__all__ = [
    "COMPLETION_RATIO",
    "continue_items",
    "position_for",
    "record_reading",
    "record_watching",
]

VAULT_ROOT_KEY = "source_vault"
#: Watching this much of a video counts as having watched it (credits are skipped).
COMPLETION_RATIO = 0.9
_READING = (UnitKind.MANGA_CHAPTER, UnitKind.ARCHIVE_PAGES)
_WATCHING = (UnitKind.EPISODE, UnitKind.VIDEO)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _project(project_key: str | None) -> str:
    if not project_key:
        return ""
    require_project_key(project_key)
    return project_key


def _series_of(session: Session, unit_key: str, relative: str) -> str | None:
    found = session.execute(
        select(CatalogUnit.series_key).where(CatalogUnit.unit_key == unit_key)
    ).scalar_one_or_none()
    if found:
        return found
    return place(relative, is_vault=True).series_key


def _upsert(session: Session, values: dict[str, Any], *, completed: bool) -> MediaProgress:
    now = _now()
    row = {
        **values,
        "profile_key": PROFILE,
        "opened_at": now,
        "completed_at": now if completed else None,
    }
    update = {
        key: row[key]
        for key in (
            "medium",
            "series_key",
            "root_key",
            "relative_path",
            "member_name",
            "page_index",
            "page_count",
            "position_ms",
            "duration_ms",
            "opened_at",
        )
    }
    statement = insert(MediaProgress).values(id=uuid7(), **row)
    statement = statement.on_conflict_do_update(
        index_elements=["profile_key", "project_key", "unit_key"],
        set_={
            **update,
            "updated_at": now,
            # Completion is remembered: re-reading a finished chapter keeps it finished.
            "completed_at": statement.excluded.completed_at
            if completed
            else MediaProgress.completed_at,
        },
    )
    session.execute(statement)
    session.flush()
    session.expire_all()
    return session.execute(
        select(MediaProgress).where(
            MediaProgress.profile_key == PROFILE,
            MediaProgress.project_key == values["project_key"],
            MediaProgress.unit_key == values["unit_key"],
        )
    ).scalar_one()


def _view(row: MediaProgress) -> dict[str, Any]:
    return {
        "unit_key": row.unit_key,
        "medium": row.medium.value,
        "series_key": row.series_key,
        "page_index": row.page_index,
        "page_count": row.page_count,
        "position_ms": row.position_ms,
        "duration_ms": row.duration_ms,
        "opened_at": row.opened_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def record_reading(
    session: Session,
    media: MediaLibrary,
    media_id: str,
    page_index: int,
    *,
    project_key: str | None = None,
) -> dict[str, Any]:
    """The reader is on ``page_index`` of an archive: remember the chapter and page."""
    try:
        described = media.describe(media_id)
        if described.view not in ("pages", "mixed"):
            raise CatalogInputError("Only an archive of pages has a reading position.")
        listing = media.archive_listing(media_id)
    except MediaUnavailableError:
        raise CatalogNotFoundError("That media is not available.") from None
    if not 0 <= page_index < len(listing.pages):
        raise CatalogInputError("That page is not in the archive.")
    label, first, count = "", 0, len(listing.pages)
    for chapter, start, pages in listing.chapters:
        if start <= page_index < start + pages:
            label, first, count = chapter, start, pages
            break
    unit_key = unit_key_for(VAULT_ROOT_KEY, described.relative, f"pages:{label}")
    row = _upsert(
        session,
        {
            "project_key": _project(project_key),
            "unit_key": unit_key,
            "medium": ProgressMedium.READING,
            "series_key": _series_of(session, unit_key, described.relative),
            "root_key": VAULT_ROOT_KEY,
            "relative_path": described.relative,
            "member_name": None,
            "page_index": page_index,
            "page_count": count,
            "position_ms": None,
            "duration_ms": None,
        },
        completed=page_index >= first + count - 1,
    )
    view = _view(row)
    view["chapter_first_page"] = first
    return view


def record_watching(
    session: Session,
    media: MediaLibrary,
    *,
    media_id: str | None = None,
    member_id: uuid.UUID | None = None,
    position_ms: int,
    duration_ms: int | None = None,
    ended: bool = False,
    project_key: str | None = None,
) -> dict[str, Any]:
    """The player is at ``position_ms``: remember the episode and the moment."""
    if (media_id is None) == (member_id is None):
        raise CatalogInputError("Name either a video or a video inside an archive.")
    if position_ms < 0 or (duration_ms is not None and duration_ms < 0):
        raise CatalogInputError("A playback position cannot be negative.")
    if member_id is not None:
        found = session.execute(
            select(CatalogMember, CatalogEntry)
            .join(CatalogEntry, CatalogEntry.id == CatalogMember.entry_id)
            .where(CatalogMember.id == member_id, CatalogMember.kind == MemberKind.VIDEO)
        ).first()
        if found is None or found[1].status is not EntryStatus.CATALOGUED:
            raise CatalogNotFoundError("That video is not in the catalog.")
        member, entry = found
        root_key, relative, member_name = entry.root_key, entry.relative_path, member.name
        unit_key = unit_key_for(root_key, relative, f"member:{member.name}")
    else:
        try:
            described = media.describe(str(media_id))
        except MediaUnavailableError:
            raise CatalogNotFoundError("That media is not available.") from None
        if described.view != "video":
            raise CatalogInputError("Only a video has a playback position.")
        root_key, relative, member_name = VAULT_ROOT_KEY, described.relative, None
        unit_key = unit_key_for(root_key, relative, "file")
    completed = ended or bool(duration_ms and position_ms >= COMPLETION_RATIO * duration_ms)
    row = _upsert(
        session,
        {
            "project_key": _project(project_key),
            "unit_key": unit_key,
            "medium": ProgressMedium.WATCHING,
            "series_key": _series_of(session, unit_key, relative),
            "root_key": root_key,
            "relative_path": relative,
            "member_name": member_name,
            "page_index": None,
            "page_count": None,
            "position_ms": position_ms,
            "duration_ms": duration_ms,
        },
        completed=completed,
    )
    return _view(row)


def position_for(
    session: Session,
    *,
    media: MediaLibrary,
    media_id: str | None = None,
    member_id: uuid.UUID | None = None,
    project_key: str | None = None,
) -> dict[str, Any] | None:
    """Where a person left a video, a video in an archive or an archive of pages."""
    where = [
        MediaProgress.profile_key == PROFILE,
        MediaProgress.project_key == _project(project_key),
    ]
    if member_id is not None:
        found = session.execute(
            select(CatalogMember.name, CatalogEntry.root_key, CatalogEntry.relative_path)
            .join(CatalogEntry, CatalogEntry.id == CatalogMember.entry_id)
            .where(CatalogMember.id == member_id)
        ).first()
        if found is None:
            return None
        where.append(
            MediaProgress.unit_key == unit_key_for(found[1], found[2], f"member:{found[0]}")
        )
    else:
        try:
            described = media.describe(str(media_id))
        except MediaUnavailableError:
            return None
        if described.view == "video":
            where.append(
                MediaProgress.unit_key == unit_key_for(VAULT_ROOT_KEY, described.relative, "file")
            )
        else:
            where.append(MediaProgress.relative_path == described.relative)
            where.append(MediaProgress.medium == ProgressMedium.READING)
    row = session.execute(
        select(MediaProgress).where(*where).order_by(MediaProgress.opened_at.desc()).limit(1)
    ).scalar_one_or_none()
    return _view(row) if row is not None else None


def continue_items(
    session: Session, *, project_key: str | None = None, limit: int = 12
) -> list[dict[str, Any]]:
    """What to pick up again: the latest unit per series, or the next one after it."""
    rows = list(
        session.execute(
            select(MediaProgress)
            .where(
                MediaProgress.profile_key == PROFILE,
                MediaProgress.project_key == _project(project_key),
            )
            .order_by(MediaProgress.opened_at.desc())
            .limit(500)
        ).scalars()
    )
    seen: set[tuple[str, str]] = set()
    items: list[dict[str, Any]] = []
    for row in rows:
        group = (row.series_key or row.unit_key, row.medium.value)
        if group in seen:
            continue
        seen.add(group)
        found = session.execute(
            select(CatalogUnit, CatalogEntry, CatalogMember)
            .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
            .outerjoin(CatalogMember, CatalogMember.id == CatalogUnit.member_id)
            .where(CatalogUnit.unit_key == row.unit_key)
        ).first()
        item: dict[str, Any] = {
            "progress": _view(row),
            "state": "resume",
            "unit": None,
            "next": None,
        }
        if found is not None:
            unit, entry, member = found
            item["unit"] = unit_view(unit, entry, member, row)
            if row.completed_at is not None:
                kinds = _READING if unit.kind in _READING else _WATCHING
                following = session.execute(
                    select(CatalogUnit, CatalogEntry, CatalogMember)
                    .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
                    .outerjoin(CatalogMember, CatalogMember.id == CatalogUnit.member_id)
                    .where(
                        CatalogUnit.series_key == unit.series_key,
                        CatalogUnit.series_key.is_not(None),
                        CatalogUnit.kind.in_(kinds),
                        CatalogUnit.sort_key > unit.sort_key,
                        CatalogEntry.status == EntryStatus.CATALOGUED,
                    )
                    .order_by(CatalogUnit.sort_key, CatalogUnit.id)
                    .limit(1)
                ).first()
                if following is not None:
                    item["state"] = "next"
                    item["next"] = unit_view(*following)
                else:
                    item["state"] = "finished"
        elif row.completed_at is not None:
            item["state"] = "finished"
        items.append(item)
        if len(items) >= limit:
            break
    return items
