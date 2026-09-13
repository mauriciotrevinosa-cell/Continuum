"""Open what the Library holds: media descriptors, pages and streams.

Every route addresses media by an **opaque id** (``m1_`` + 32 hex). There is
no route, parameter or header through which a client can name a file (F-50):
ids come from the engine's own listing, are resolved by the storage layer
against the configured Source Vault, and are read, never written (ADR-0001).

A work's openable units come from the acquisition engine's coverage document,
which already knows which files make up which work. This router only turns
those Vault-relative names into ids and descriptors; it decides nothing about
what a file is part of.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from continuum_storage import (
    MEDIA_ID_PATTERN,
    AcquisitionStore,
    MediaFile,
    MediaLibrary,
    MediaUnavailableError,
)
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi import Path as PathParam
from starlette.responses import Response, StreamingResponse

from continuum_api import library_projection as lp
from continuum_api.schemas import (
    ArchiveListingOut,
    ArchivePageOut,
    ChapterGroup,
    ContainedVideo,
    MediaDetail,
    MediaStatus,
    MediaUnit,
    WorkMedia,
)

router = APIRouter(prefix="/library/media", tags=["media"])

MediaId = Annotated[str, PathParam(pattern=MEDIA_ID_PATTERN)]
#: Browsers play these natively. MKV and MOV often play in Chromium-based
#: browsers depending on the codecs inside; the viewer finds out by trying.
_PLAYS = {".mp4": "yes", ".m4v": "yes", ".webm": "yes", ".mkv": "maybe", ".mov": "maybe"}
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_NOT_FOUND = "media not found"


def _library(request: Request) -> MediaLibrary:
    library: MediaLibrary = request.app.state.media
    return library


def _store(request: Request) -> AcquisitionStore:
    store: AcquisitionStore = request.app.state.acquisition
    return store


def _not_found() -> HTTPException:
    # One answer for malformed, unknown, stale and escaping ids alike.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


# -- context -----------------------------------------------------------------
def _works(store: AcquisitionStore) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """(coverage works, work id -> layout row with family context)."""
    coverage = (store.read("vault-coverage.json") or {}).get("works") or {}
    rows: dict[str, dict[str, Any]] = {}
    for family in (store.read("vault-layout.json") or {}).get("families") or []:
        for row in family.get("works") or []:
            rows[str(row.get("work_id") or "")] = dict(
                row,
                _family_id=family.get("family_id"),
                _family_title=family.get("family_title"),
                _family_path=family.get("family_path"),
            )
    return coverage, rows


def _unit(media: MediaFile, engine_unit: dict[str, Any] | None) -> MediaUnit:
    info = engine_unit or {}
    season = info.get("season")
    episode = info.get("episode")
    chapter_text = str(info.get("chapter_text") or "")
    volumes = [int(v) for v in (info.get("volumes") or [])]
    if episode is not None:
        label = f"S{season} · E{episode}" if season else f"Episode {episode}"
        if season == 0:
            label = f"Special {episode}"
    elif volumes and len(volumes) == 1:
        label = f"Volume {volumes[0]}"
    elif chapter_text:
        label = f"Chapters {chapter_text}"
    else:
        label = media.name.rsplit(".", 1)[0]
    contained = [
        ContainedVideo(
            name=str(entry.get("name") or ""),
            size_bytes=int(entry.get("size") or 0),
            season=(eps[i].get("season") if i < len(eps) else None),
            episode=(eps[i].get("episode") if i < len(eps) else None),
        )
        for eps in [list(info.get("contained_episodes") or [])]
        for i, entry in enumerate(media.archive_video_entries)
    ]
    return MediaUnit(
        id=media.id,
        name=media.name,
        kind=media.kind,
        view=media.view,  # type: ignore[arg-type]
        size_bytes=media.size_bytes,
        label=label,
        season=season,
        episode=episode,
        chapters=int(info.get("chapters") or 0),
        chapter_text=chapter_text,
        volumes=volumes,
        pages=media.archive_images,
        contained_videos=media.archive_videos,
        contained=contained,
        plays_in_browser=_plays(media),
    )


def _plays(media: MediaFile) -> Literal["yes", "maybe", "no"]:
    if media.view != "video":
        return "no"
    verdict = _PLAYS.get(media.extension)
    return "yes" if verdict == "yes" else "maybe" if verdict == "maybe" else "no"


def _work_units(library: MediaLibrary, cov: dict[str, Any]) -> list[MediaUnit]:
    engine_units = {str(u.get("file")): u for u in (cov.get("units") or []) if isinstance(u, dict)}
    order = [str(u.get("file")) for u in (cov.get("units") or []) if isinstance(u, dict)]
    for rel in cov.get("media_files") or []:
        if rel not in engine_units:
            order.append(str(rel))
    out: list[MediaUnit] = []
    for rel in order:
        media = library.describe_relative(rel)
        if media is not None:
            out.append(_unit(media, engine_units.get(rel)))
    return out


# -- routes --------------------------------------------------------------------
@router.get("/status", response_model=MediaStatus)
def media_status(request: Request) -> MediaStatus:
    available, reason = _library(request).status()
    return MediaStatus(available=available, reason=reason)


@router.get("", response_model=WorkMedia)
def list_media(
    request: Request,
    work: Annotated[str | None, Query(max_length=200)] = None,
    family: Annotated[str | None, Query(max_length=160)] = None,
    material: Annotated[str | None, Query(max_length=40)] = None,
) -> WorkMedia:
    """The openable units of one work, or of a family's unmatched material.

    ``work`` and ``family`` are catalogue ids; they index documents already in
    memory and never reach the filesystem.
    """
    library = _library(request)
    store = _store(request)
    available, reason = library.status()
    coverage, rows = _works(store)
    if work:
        row = rows.get(work)
        cov = coverage.get(work)
        if row is None or not isinstance(cov, dict):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="work not found")
        return WorkMedia(
            available=available,
            reason=reason,
            work_id=work,
            title=str(row.get("work") or ""),
            family_id=str(row.get("_family_id") or ""),
            family_title=str(row.get("_family_title") or ""),
            material_class=row.get("material_class"),
            relation=row.get("relationship_type"),
            state=lp.work_state(row.get("coverage_status"), stale_family=False),  # type: ignore[arg-type]
            coverage_reason=str(cov.get("reason") or ""),
            units=_work_units(library, cov),
        )
    if family and material:
        layout = store.read("vault-layout.json") or {}
        for fam in layout.get("families") or []:
            if str(fam.get("family_id")) != family:
                continue
            classes = fam.get("classes") if isinstance(fam.get("classes"), dict) else {}
            info = classes.get(material.lower()) if isinstance(classes, dict) else None
            rels = (info or {}).get("unattributed_rels") or []
            units = [
                _unit(media, None)
                for media in (library.describe_relative(str(rel)) for rel in rels)
                if media is not None
            ]
            return WorkMedia(
                available=available,
                reason=reason,
                title=f"Unmatched {material}",
                family_id=family,
                family_title=str(fam.get("family_title") or ""),
                material_class=material.lower(),
                state="NEEDS_MAPPING",
                unmapped=True,
                units=units,
            )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="family not found")
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="give a work, or a family and a material",
    )


@router.get("/{media_id}", response_model=MediaDetail)
def media_detail(request: Request, media_id: MediaId) -> MediaDetail:
    library = _library(request)
    try:
        media = library.describe(media_id)
    except MediaUnavailableError:
        raise _not_found() from None
    coverage, rows = _works(_store(request))
    for work_id, cov in coverage.items():
        if not isinstance(cov, dict) or media.relative not in (cov.get("media_files") or []):
            continue
        units = _work_units(library, cov)
        ids = [u.id for u in units]
        position = ids.index(media_id) if media_id in ids else -1
        row = rows.get(work_id, {})
        return MediaDetail(
            unit=units[position] if position >= 0 else _unit(media, None),
            work_id=work_id,
            work_title=str(row.get("work") or cov.get("work") or ""),
            family_id=str(row.get("_family_id") or ""),
            family_title=str(row.get("_family_title") or cov.get("family") or ""),
            material_class=row.get("material_class"),
            position=position,
            total=len(units),
            previous_id=ids[position - 1] if position > 0 else None,
            next_id=ids[position + 1] if 0 <= position < len(ids) - 1 else None,
        )
    return MediaDetail(unit=_unit(media, None))


@router.get("/{media_id}/pages", response_model=ArchiveListingOut)
def media_pages(request: Request, media_id: MediaId) -> ArchiveListingOut:
    try:
        listing = _library(request).archive_listing(media_id)
    except MediaUnavailableError:
        raise _not_found() from None
    return ArchiveListingOut(
        pages=[
            ArchivePageOut(index=p.index, label=p.label, chapter=p.chapter) for p in listing.pages
        ],
        chapters=[ChapterGroup(label=c[0], first=c[1], count=c[2]) for c in listing.chapters],
        videos=[
            ContainedVideo(name=str(v.get("name") or ""), size_bytes=int(v.get("size") or 0))
            for v in listing.videos
        ],
        other_entries=listing.other_entries,
    )


@router.get("/{media_id}/pages/{index}")
def media_page(
    request: Request, media_id: MediaId, index: Annotated[int, PathParam(ge=0, le=100_000)]
) -> Response:
    try:
        data, content_type = _library(request).archive_page(media_id, index)
    except MediaUnavailableError:
        raise _not_found() from None
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{media_id}/content")
def media_content(request: Request, media_id: MediaId) -> Response:
    """Stream a video or document, honouring a single byte range.

    Seeking in a player is a Range request; without it a two-gigabyte episode
    would have to be read from the start to watch its last minute.
    """
    library = _library(request)
    header = request.headers.get("range")
    start, end = 0, None
    if header:
        match = _RANGE.match(header.strip())
        if not match or (not match.group(1) and not match.group(2)):
            return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
        try:
            size = library.describe(media_id).size_bytes
        except MediaUnavailableError:
            raise _not_found() from None
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else None
        else:  # "bytes=-N": the last N bytes
            start = max(size - int(match.group(2)), 0)
    try:
        media, first, last, body = library.open_range(media_id, start, end)
    except MediaUnavailableError:
        raise _not_found() from None
    except ValueError:
        return Response(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(last - first + 1),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-transform",
    }
    code = status.HTTP_200_OK
    if header:
        headers["Content-Range"] = f"bytes {first}-{last}/{media.size_bytes}"
        code = status.HTTP_206_PARTIAL_CONTENT
    return StreamingResponse(
        body,
        status_code=code,
        media_type=media.content_type or "application/octet-stream",
        headers=headers,
    )
