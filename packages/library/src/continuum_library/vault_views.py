"""Retrieval over the full-Vault catalog: series, units, entries and search.

Views are plain dictionaries for the API. They name a unit by its catalog id,
a Vault file by its opaque media id and an archive member by its member id -
never by a path a client could send back. What a person needs to recognise a
file (its name, the member's name, its series) is included; where it lives on
disk is not.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from continuum_core.catalog import (
    Confidence,
    EntryStatus,
    MaterialClass,
    MemberKind,
    ProgressMedium,
    UnitKind,
)
from continuum_db.models import (
    CatalogEntry,
    CatalogMember,
    CatalogUnit,
    MediaProgress,
    MusicReference,
    ReferenceCandidate,
    ReferenceItem,
)
from continuum_storage import ProjectLibrary, media_id_for
from sqlalchemy import Integer, Select, Text, cast, func, select
from sqlalchemy.orm import Session

from continuum_library.validation import CatalogInputError, CatalogNotFoundError

__all__ = [
    "PROFILE",
    "entry_list",
    "search_everything",
    "series_detail",
    "series_list",
    "unit_detail",
    "unit_search",
    "unit_view",
]

PROFILE = "local"
VAULT_ROOT_KEY = "source_vault"
MAX_LIMIT = 500
_READING = (UnitKind.MANGA_CHAPTER, UnitKind.ARCHIVE_PAGES)
_WATCHING = (UnitKind.EPISODE, UnitKind.VIDEO)


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    return text


def _words(q: str | None) -> list[str]:
    if not q:
        return []
    words = [w for w in q.lower().replace("_", " ").split() if w]
    if len(words) > 12 or any(len(w) > 80 for w in words):
        raise CatalogInputError("Search with a few shorter words.")
    return words


def _open_link(
    unit: CatalogUnit, entry: CatalogEntry, member: CatalogMember | None
) -> dict[str, Any]:
    """How the Studio opens a unit, in ids only."""
    if entry.status is not EntryStatus.CATALOGUED:
        return {"kind": "none"}
    if entry.root_key != VAULT_ROOT_KEY:
        return {"kind": "intake"}
    media_id = media_id_for(entry.relative_path)
    if unit.kind in _READING:
        return {"kind": "reader", "media_id": media_id, "page_index": unit.first_page_index or 0}
    if unit.kind in _WATCHING and member is not None:
        return {"kind": "member", "media_id": media_id, "member_id": str(member.id)}
    if unit.kind in _WATCHING:
        return {"kind": "player", "media_id": media_id}
    if unit.kind is UnitKind.IMAGE:
        return {"kind": "image", "media_id": media_id}
    if unit.kind is UnitKind.DOCUMENT:
        return {"kind": "document", "media_id": media_id}
    return {"kind": "none"}


def _progress_view(row: MediaProgress | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "medium": row.medium.value,
        "page_index": row.page_index,
        "page_count": row.page_count,
        "position_ms": row.position_ms,
        "duration_ms": row.duration_ms,
        "opened_at": _iso(row.opened_at),
        "completed_at": _iso(row.completed_at),
    }


def unit_view(
    unit: CatalogUnit,
    entry: CatalogEntry,
    member: CatalogMember | None = None,
    progress: MediaProgress | None = None,
) -> dict[str, Any]:
    return {
        "id": str(unit.id),
        "unit_key": unit.unit_key,
        "kind": unit.kind.value,
        "label": unit.label,
        "material_class": unit.material_class.value,
        "collection": unit.collection,
        "series_key": unit.series_key,
        "series_title": unit.series_title,
        "program_title": unit.program_title,
        "subseries": unit.subseries,
        "season": unit.season,
        "episode": unit.episode,
        "episode_kind": unit.episode_kind.value if unit.episode_kind else None,
        "chapter_number": _number(unit.chapter_number),
        "volume": unit.volume,
        "first_page_index": unit.first_page_index,
        "page_count": unit.page_count,
        "confidence": unit.confidence.value,
        "evidence": list(unit.evidence or []),
        "flags": list(unit.flags or []),
        "source": {
            "entry_id": str(entry.id),
            "root_key": entry.root_key,
            "collection": entry.collection,
            "file_name": entry.file_name,
            "status": entry.status.value,
            "detected_format": entry.detected_format,
            "archive_view": entry.archive_view,
            "byte_size": int(entry.byte_size),
            "content_hash": entry.content_hash,
            "member_id": str(member.id) if member is not None else None,
            "member_name": member.name.rsplit("/", 1)[-1] if member is not None else None,
            "member_bytes": int(member.byte_size) if member is not None else None,
            "member_cached": bool(member is not None and member.cached_sha256),
            "creator_handle": (entry.facts or {}).get("creator_handle"),
            "posted_at": (entry.facts or {}).get("posted_at"),
        },
        "open": _open_link(unit, entry, member),
        "progress": _progress_view(progress),
    }


def _joined() -> Select[tuple[CatalogUnit, CatalogEntry, CatalogMember]]:
    return (
        select(CatalogUnit, CatalogEntry, CatalogMember)
        .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
        .outerjoin(CatalogMember, CatalogMember.id == CatalogUnit.member_id)
    )


def _progress_for(
    session: Session, keys: Sequence[str], project_key: str = ""
) -> dict[str, MediaProgress]:
    if not keys:
        return {}
    rows = session.execute(
        select(MediaProgress).where(
            MediaProgress.profile_key == PROFILE,
            MediaProgress.project_key == project_key,
            MediaProgress.unit_key.in_(list(keys)),
        )
    ).scalars()
    return {row.unit_key: row for row in rows}


def _views(session: Session, rows: Sequence[Any]) -> list[dict[str, Any]]:
    progress = _progress_for(session, [row[0].unit_key for row in rows])
    return [unit_view(u, e, m, progress.get(u.unit_key)) for u, e, m in rows]


# ---------------------------------------------------------------------------
def series_list(
    session: Session, *, q: str | None = None, material: MaterialClass | None = None
) -> list[dict[str, Any]]:
    """Every series the catalog knows, with what it holds and where you left off."""
    present = (CatalogEntry.status != EntryStatus.MISSING) & CatalogEntry.duplicate_of_id.is_(None)
    query = (
        select(
            CatalogUnit.series_key,
            func.min(CatalogUnit.series_title),
            CatalogUnit.material_class,
            CatalogUnit.kind,
            func.count(),
            func.sum(cast(func.jsonb_array_length(CatalogUnit.flags) > 0, Integer)),
        )
        .join(CatalogEntry, CatalogEntry.id == CatalogUnit.entry_id)
        .where(CatalogUnit.series_key.is_not(None), present)
        .group_by(CatalogUnit.series_key, CatalogUnit.material_class, CatalogUnit.kind)
    )
    for word in _words(q):
        query = query.where(CatalogUnit.search_text.contains(word, autoescape=True))
    if material is not None:
        query = query.where(CatalogUnit.material_class == material)
    series: dict[str, dict[str, Any]] = {}
    for key, title, mat, kind, count, flagged in session.execute(query).all():
        row = series.setdefault(
            key,
            {"series_key": key, "title": title, "materials": {}, "units": {}, "flagged": 0},
        )
        row["materials"][mat.value] = row["materials"].get(mat.value, 0) + int(count)
        row["units"][kind.value] = row["units"].get(kind.value, 0) + int(count)
        row["flagged"] += int(flagged or 0)
    last_opened: dict[str | None, dt.datetime] = {
        row[0]: row[1]
        for row in session.execute(
            select(MediaProgress.series_key, func.max(MediaProgress.opened_at))
            .where(MediaProgress.profile_key == PROFILE, MediaProgress.series_key.is_not(None))
            .group_by(MediaProgress.series_key)
        ).all()
    }
    for key, row in series.items():
        opened = last_opened.get(key)
        row["last_opened_at"] = _iso(opened) if isinstance(opened, dt.datetime) else None
    return sorted(series.values(), key=lambda r: (r["title"] or "").lower())


def series_detail(session: Session, series_key: str) -> dict[str, Any]:
    rows = session.execute(
        _joined()
        .where(
            CatalogUnit.series_key == series_key,
            CatalogEntry.status != EntryStatus.MISSING,
            CatalogEntry.duplicate_of_id.is_(None),
        )
        .order_by(CatalogUnit.sort_key, CatalogUnit.id)
    ).all()
    duplicate_copies = session.execute(
        select(func.count(func.distinct(CatalogEntry.id)))
        .join(CatalogUnit, CatalogUnit.entry_id == CatalogEntry.id)
        .where(CatalogUnit.series_key == series_key, CatalogEntry.duplicate_of_id.is_not(None))
    ).scalar_one()
    if not rows:
        raise CatalogNotFoundError("That series is not in the catalog.")
    views = _views(session, rows)
    reading = [v for v in views if v["kind"] in {k.value for k in _READING}]
    watching = [v for v in views if v["kind"] in {k.value for k in _WATCHING}]
    other = [v for v in views if v not in reading and v not in watching]
    seasons: dict[str, list[dict[str, Any]]] = {}
    for view in watching:
        label = "Season ?" if view["season"] is None else f"Season {view['season']}"
        if view["episode_kind"] in ("MOVIE", "OVA", "SPECIAL") and view["season"] is None:
            label = {"MOVIE": "Films", "OVA": "OVA", "SPECIAL": "Specials"}[view["episode_kind"]]
        if view["kind"] == UnitKind.VIDEO.value:
            label = "Other videos"
        if view["subseries"]:
            program = view["subseries"]
            label = program if view["season"] is None else f"{program} · {label}"
        seasons.setdefault(label, []).append(view)
    works: dict[str, list[dict[str, Any]]] = {}
    for view in reading:
        works.setdefault(view["subseries"] or "", []).append(view)
    return {
        "series_key": series_key,
        "title": rows[0][0].series_title,
        "reading": reading,
        # The series' own work first (""), then each other work in its folder.
        "reading_groups": [{"label": label, "units": units} for label, units in works.items()],
        "watching": [{"label": label, "units": units} for label, units in seasons.items()],
        "other": other,
        "progress": series_progress(session, series_key),
        "uncertain": sum(1 for v in views if v["confidence"] == Confidence.LOW.value),
        # Exact byte copies of files shown above are linked, not listed twice.
        "duplicate_copies_hidden": int(duplicate_copies),
    }


def series_progress(session: Session, series_key: str, project_key: str = "") -> dict[str, Any]:
    """Last opened and last completed unit per medium, for "Continue"."""
    out: dict[str, Any] = {}
    for medium in (ProgressMedium.READING, ProgressMedium.WATCHING):
        base = select(MediaProgress).where(
            MediaProgress.profile_key == PROFILE,
            MediaProgress.project_key == project_key,
            MediaProgress.series_key == series_key,
            MediaProgress.medium == medium,
        )
        opened = session.execute(
            base.order_by(MediaProgress.opened_at.desc()).limit(1)
        ).scalar_one_or_none()
        completed = session.execute(
            base.where(MediaProgress.completed_at.is_not(None))
            .order_by(MediaProgress.completed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        out[medium.value.lower()] = {
            "last_opened": _progress_ref(session, opened),
            "last_completed": _progress_ref(session, completed),
        }
    return out


def _progress_ref(session: Session, row: MediaProgress | None) -> dict[str, Any] | None:
    if row is None:
        return None
    found = session.execute(_joined().where(CatalogUnit.unit_key == row.unit_key)).first()
    view = {"unit_key": row.unit_key, "progress": _progress_view(row)}
    if found is not None:
        view["unit"] = unit_view(found[0], found[1], found[2], row)
    return view


def unit_search(
    session: Session,
    *,
    q: str | None = None,
    series_key: str | None = None,
    kind: UnitKind | None = None,
    material: MaterialClass | None = None,
    season: int | None = None,
    episode: int | None = None,
    chapter: Decimal | None = None,
    collection: str | None = None,
    creator: str | None = None,
    confidence: Confidence | None = None,
    root_key: str | None = None,
    vault_relative: str | None = None,
    include_duplicates: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    query = _joined().where(CatalogEntry.status != EntryStatus.MISSING)
    if not include_duplicates:
        query = query.where(CatalogEntry.duplicate_of_id.is_(None))
    for word in _words(q):
        query = query.where(CatalogUnit.search_text.contains(word, autoescape=True))
    if series_key:
        query = query.where(CatalogUnit.series_key == series_key)
    if kind is not None:
        query = query.where(CatalogUnit.kind == kind)
    if material is not None:
        query = query.where(CatalogUnit.material_class == material)
    if season is not None:
        query = query.where(CatalogUnit.season == season)
    if episode is not None:
        query = query.where(CatalogUnit.episode == episode)
    if chapter is not None:
        query = query.where(CatalogUnit.chapter_number == chapter)
    if collection:
        query = query.where(CatalogUnit.collection == collection)
    if creator:
        query = query.where(
            CatalogEntry.facts["creator_handle"].astext.ilike(f"%{creator.strip('@')}%")
        )
    if confidence is not None:
        query = query.where(CatalogUnit.confidence == confidence)
    if root_key:
        query = query.where(CatalogEntry.root_key == root_key)
    if vault_relative is not None:
        # One held file's units; the relative path comes from the media id, never a client.
        query = query.where(
            CatalogEntry.root_key == VAULT_ROOT_KEY, CatalogEntry.relative_path == vault_relative
        )
    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = session.execute(
        query.order_by(CatalogUnit.series_key, CatalogUnit.sort_key, CatalogUnit.id)
        .limit(max(1, min(limit, MAX_LIMIT)))
        .offset(max(0, offset))
    ).all()
    return {"total": int(total), "units": _views(session, rows)}


def unit_detail(session: Session, unit_id: uuid.UUID) -> dict[str, Any]:
    found = session.execute(_joined().where(CatalogUnit.id == unit_id)).first()
    if found is None:
        raise CatalogNotFoundError("That unit is not in the catalog.")
    unit, entry, member = found
    view = unit_view(
        unit, entry, member, _progress_for(session, [unit.unit_key]).get(unit.unit_key)
    )
    siblings = session.execute(
        select(CatalogUnit.id, CatalogUnit.label, CatalogUnit.sort_key)
        .where(
            CatalogUnit.series_key == unit.series_key,
            CatalogUnit.kind == unit.kind,
            CatalogUnit.series_key.is_not(None),
        )
        .order_by(CatalogUnit.sort_key, CatalogUnit.id)
    ).all()
    ids = [row[0] for row in siblings]
    position = ids.index(unit.id) if unit.id in ids else -1
    view["previous_id"] = str(ids[position - 1]) if position > 0 else None
    view["next_id"] = str(ids[position + 1]) if 0 <= position < len(ids) - 1 else None
    view["provenance"] = {
        "series": unit.series_title,
        "entry": entry.file_name,
        "member": member.name if member is not None else None,
        "unit": unit.label,
        "entry_hash": entry.content_hash,
        "hash_source": entry.hash_source.value if entry.hash_source else None,
        "scanner_facts": {
            k: v for k, v in (entry.facts or {}).items() if k not in ("placement_evidence",)
        },
    }
    return view


def entry_list(
    session: Session,
    *,
    root_key: str | None = None,
    status: EntryStatus | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Files as the catalog observed them - the coverage drill-down."""
    query = select(CatalogEntry)
    if root_key:
        query = query.where(CatalogEntry.root_key == root_key)
    if status is not None:
        query = query.where(CatalogEntry.status == status)
    for word in _words(q):
        query = query.where(func.lower(CatalogEntry.relative_path).contains(word, autoescape=True))
    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    rows = session.execute(
        query.order_by(CatalogEntry.root_key, CatalogEntry.relative_path)
        .limit(max(1, min(limit, MAX_LIMIT)))
        .offset(max(0, offset))
    ).scalars()
    members: dict[uuid.UUID, int] = {
        row[0]: int(row[1])
        for row in session.execute(
            select(CatalogMember.entry_id, func.count())
            .where(CatalogMember.kind == MemberKind.VIDEO)
            .group_by(CatalogMember.entry_id)
        ).all()
    }
    return {
        "total": int(total),
        "entries": [
            {
                "id": str(e.id),
                "root_key": e.root_key,
                "collection": e.collection,
                # Shown to people so they can find the file; never accepted as input.
                "display_path": e.relative_path,
                "file_name": e.file_name,
                "status": e.status.value,
                "reason": e.status_reason,
                "error": e.last_error,
                "detected_kind": e.detected_kind.value,
                "detected_format": e.detected_format,
                "material_class": e.material_class.value,
                "series_title": e.series_title,
                "archive_view": e.archive_view,
                "members": int(e.member_count),
                "video_members": int(members.get(e.id, 0)),
                "byte_size": int(e.byte_size),
                "hashed": bool(e.content_hash),
                "duplicate_of": str(e.duplicate_of_id) if e.duplicate_of_id else None,
                "media_id": media_id_for(e.relative_path) if e.root_key == VAULT_ROOT_KEY else None,
                "flags": list((e.facts or {}).get("placement_flags") or []),
                "missing_since": _iso(e.missing_since),
            }
            for e in rows
        ],
    }


def search_everything(
    session: Session, q: str, *, projects: ProjectLibrary | None = None, limit: int = 30
) -> dict[str, Any]:
    """One box, the whole Studio: Vault units, references, inbox, project documents, music."""
    words = _words(q)
    if not words:
        raise CatalogInputError("Type something to search for.")
    limit = max(1, min(limit, 100))
    units = unit_search(session, q=q, limit=limit)

    reference_text = func.lower(
        func.concat_ws(
            " ",
            ReferenceItem.label,
            ReferenceItem.notes,
            ReferenceItem.creator_handle,
            ReferenceItem.collection,
            ReferenceItem.provenance["original_file_name"].astext,
            ReferenceItem.provenance["source_title"].astext,
        )
    )
    reference_query = select(ReferenceItem).where(ReferenceItem.removed_at.is_(None))
    for word in words:
        reference_query = reference_query.where(reference_text.contains(word, autoescape=True))
    references = [
        {
            "id": str(r.id),
            "label": r.label,
            "origin": r.origin.value,
            "reference_class": r.reference_class.value,
            "collection": r.collection,
            "creator_handle": r.creator_handle,
            "rights_status": r.rights_status.value,
            "training_eligibility": r.training_eligibility.value,
        }
        for r in session.execute(
            reference_query.order_by(ReferenceItem.created_at.desc(), ReferenceItem.id).limit(limit)
        ).scalars()
    ]

    candidate_text = func.lower(
        func.concat_ws(
            " ",
            ReferenceCandidate.display_name,
            ReferenceCandidate.creator_handle,
            ReferenceCandidate.collection,
            ReferenceCandidate.notes,
            cast(ReferenceCandidate.tags, Text),
        )
    )
    candidate_query = select(ReferenceCandidate)
    for word in words:
        candidate_query = candidate_query.where(candidate_text.contains(word, autoescape=True))
    candidates = [
        {
            "id": str(c.id),
            "display_name": c.display_name,
            "status": c.status.value,
            "intake_kind": c.intake_kind.value,
            "creator_handle": c.creator_handle,
            "collection": c.collection,
        }
        for c in session.execute(
            candidate_query.order_by(
                ReferenceCandidate.created_at.desc(), ReferenceCandidate.id
            ).limit(limit)
        ).scalars()
    ]

    documents: list[dict[str, Any]] = []
    for project in projects.projects() if projects is not None else []:
        for document in project.documents:
            haystack = " ".join(
                [
                    document.title,
                    document.id,
                    document.summary,
                    document.category,
                    document.episode or "",
                ]
            ).lower()
            if all(word in haystack for word in words):
                documents.append(
                    {
                        "project_id": project.id,
                        "project_title": project.title,
                        "id": document.id,
                        "title": document.title,
                        "lifecycle": document.lifecycle,
                        "episode": document.episode,
                    }
                )

    music_text = func.lower(
        func.concat_ws(
            " ",
            MusicReference.track,
            MusicReference.artist,
            MusicReference.mood,
            MusicReference.intended_use,
            MusicReference.scene,
            MusicReference.episode,
            MusicReference.notes,
        )
    )
    music_query = select(MusicReference).where(MusicReference.removed_at.is_(None))
    for word in words:
        music_query = music_query.where(music_text.contains(word, autoescape=True))
    music = [
        {"id": str(m.id), "project_key": m.project_key, "track": m.track, "artist": m.artist}
        for m in session.execute(music_query.order_by(MusicReference.track).limit(limit)).scalars()
    ]
    return {
        "query": q,
        "units": units,
        "references": references,
        "candidates": candidates,
        "documents": documents[:limit],
        "music": music,
    }
