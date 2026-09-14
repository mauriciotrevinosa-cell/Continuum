"""The full-Vault catalog: scans, coverage, retrieval, progress and archived video.

Every route addresses records by id or key - a root key such as
``source_vault``, a series key, a unit or member UUID, an opaque media id - and
never by a path (F-50). Scans, hash passes, imports and member extractions are
**enqueued**; the worker runs them (ADR-0002). Nothing here can write to the
Source Vault or an intake folder: the only bytes this router serves beyond JSON
are archive members the worker already extracted into the managed cache.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from continuum_core import ContinuumError
from continuum_core.catalog import Confidence, EntryStatus, MaterialClass, UnitKind
from continuum_db.models import CatalogScan, Job
from continuum_db.session import session_scope
from continuum_library import CatalogInputError, CatalogNotFoundError
from continuum_library.collection_import import import_report
from continuum_library.coverage import build_coverage, render_coverage_markdown
from continuum_library.members import MEMBER_TYPES, member_record, member_state, prepare_member
from continuum_library.progress import (
    continue_items,
    position_for,
    record_reading,
    record_watching,
)
from continuum_library.vault_jobs import request_hash, request_import, request_scan
from continuum_library.vault_views import (
    entry_list,
    search_everything,
    series_detail,
    series_list,
    unit_detail,
    unit_search,
)
from continuum_storage import (
    MEDIA_ID_PATTERN,
    MediaLibrary,
    MediaUnavailableError,
    ProjectLibrary,
    catalog_roots,
)
from continuum_storage.member_cache import MemberCache
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse, Response, StreamingResponse

router = APIRouter(prefix="/catalog", tags=["catalog"])

#: An intake collection, by the slug of its root key (``intake:<slug>``).
CollectionSlug = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,39}$")]
SeriesKey = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,119}$")]
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScanRequest(StrictBody):
    #: Root keys to scan; empty means every configured root.
    root_keys: list[
        Annotated[str, Field(pattern=r"^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$")]
    ] = []
    hash: bool = True


class ReadingIn(StrictBody):
    media_id: Annotated[str, Field(pattern=MEDIA_ID_PATTERN)]
    page_index: Annotated[int, Field(ge=0, le=100_000)]
    project_key: Annotated[str | None, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")] = None


class WatchingIn(StrictBody):
    media_id: Annotated[str | None, Field(pattern=MEDIA_ID_PATTERN)] = None
    member_id: uuid.UUID | None = None
    position_ms: Annotated[int, Field(ge=0, le=100 * 3600 * 1000)]
    duration_ms: Annotated[int | None, Field(ge=0, le=100 * 3600 * 1000)] = None
    ended: bool = False
    project_key: Annotated[str | None, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")] = None


# ---------------------------------------------------------------------------
@contextmanager
def scope(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        try:
            yield session
        except CatalogNotFoundError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail=_detail(exc)) from None
        except CatalogInputError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=_detail(exc)) from None


def _detail(exc: ContinuumError) -> dict[str, Any]:
    return {"error": exc.code, "message": exc.user_message, "remediation": exc.remediation}


def _roots(request: Request) -> list[Any]:
    return catalog_roots(request.app.state.settings)


def _root_keys(request: Request) -> set[str]:
    return {root.key for root in _roots(request)}


def _media(request: Request) -> MediaLibrary:
    media: MediaLibrary = request.app.state.media
    return media


def _cache(request: Request) -> MemberCache:
    settings = request.app.state.settings
    return MemberCache(
        request.app.state.storage.derived,
        budget_bytes=settings.member_cache_bytes,
        max_member_bytes=settings.member_cache_max_member_bytes,
    )


def _projects(request: Request) -> ProjectLibrary:
    projects: ProjectLibrary = request.app.state.projects
    return projects


def _job(job: Job | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status.value,
        "units_total": job.units_total,
        "units_done": job.units_done,
    }


# -- roots and scans -------------------------------------------------------------
@router.get("/roots")
def roots(request: Request) -> list[dict[str, Any]]:
    """The folders the catalog covers, whether they are reachable, and their last scan."""
    out: list[dict[str, Any]] = []
    with scope(request) as session:
        for root in _roots(request):
            latest = session.execute(
                select(CatalogScan)
                .where(CatalogScan.root_key == root.key)
                .order_by(CatalogScan.started_at.desc(), CatalogScan.id.desc())
                .limit(1)
            ).scalar_one_or_none()
            active = session.execute(
                select(Job)
                .where(
                    Job.payload["root_key"].astext == root.key,
                    Job.status.not_in(["SUCCEEDED", "FAILED_FINAL", "CANCELLED"]),
                )
                .order_by(Job.created_at)
            ).scalars()
            out.append(
                {
                    "root_key": root.key,
                    "collection": root.collection,
                    "material": root.material,
                    "available": root.available(),
                    "last_scan": {
                        "id": str(latest.id),
                        "status": latest.status.value,
                        "started_at": latest.started_at.isoformat(),
                        "finished_at": latest.finished_at.isoformat()
                        if latest.finished_at
                        else None,
                        "counts": latest.counts,
                        "files": (latest.survey or {}).get("files"),
                        "skipped": (latest.survey or {}).get("skipped"),
                    }
                    if latest is not None
                    else None,
                    "active_jobs": [_job(job) for job in active],
                }
            )
    return out


@router.post("/scans", status_code=202)
def start_scan(request: Request, body: ScanRequest) -> list[dict[str, Any]]:
    """Queue a scan (and a hash pass after it) of the named roots, or of all of them."""
    known = _root_keys(request)
    wanted = body.root_keys or sorted(known)
    unknown = [key for key in wanted if key not in known]
    if unknown:
        raise HTTPException(status_code=404, detail={"message": "That folder is not configured."})
    with scope(request) as session:
        requested = request_scan(session, wanted, hash_after=body.hash)
        return [
            {
                "root_key": r.root_key,
                "scan": _job(r.scan),
                "hash": _job(r.hash),
                "created": r.created,
            }
            for r in requested
        ]


class HashRequest(StrictBody):
    root_key: Annotated[str, Field(pattern=r"^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$")]


@router.post("/hash", status_code=202)
def start_hash(request: Request, body: HashRequest) -> dict[str, Any] | None:
    """Queue a hash pass over files that have no hash for their current size and mtime."""
    if body.root_key not in _root_keys(request):
        raise HTTPException(status_code=404, detail={"message": "That folder is not configured."})
    with scope(request) as session:
        return _job(request_hash(session, body.root_key))


@router.get("/coverage")
def coverage(request: Request) -> dict[str, Any]:
    """The coverage audit, computed from the catalog now."""
    with scope(request) as session:
        return build_coverage(session, _roots(request), projects=_projects(request))


@router.get("/coverage/markdown", response_class=PlainTextResponse)
def coverage_markdown(request: Request) -> PlainTextResponse:
    with scope(request) as session:
        report = build_coverage(session, _roots(request), projects=_projects(request))
    return PlainTextResponse(
        render_coverage_markdown(report), media_type="text/markdown; charset=utf-8"
    )


# -- collections ---------------------------------------------------------------------
def _collection(request: Request, slug: str) -> Any:
    root = next((r for r in _roots(request) if r.key == f"intake:{slug}"), None)
    if root is None:
        raise HTTPException(
            status_code=404, detail={"message": "That intake folder is not configured."}
        )
    return root


@router.post("/collections/{slug}/import", status_code=202)
def start_import(request: Request, slug: CollectionSlug) -> dict[str, Any]:
    """Rescan an intake collection, hash it, and import it as references."""
    root = _collection(request, slug)
    with scope(request) as session:
        requested = request_import(session, root.key)
        return {"root_key": root.key, "scan": _job(requested.scan), "import": _job(requested.hash)}


@router.get("/collections/{slug}/import")
def import_status(request: Request, slug: CollectionSlug) -> dict[str, Any]:
    root = _collection(request, slug)
    with scope(request) as session:
        return import_report(session, root)


# -- retrieval -----------------------------------------------------------------------
@router.get("/series")
def list_series(
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    material: MaterialClass | None = None,
) -> list[dict[str, Any]]:
    with scope(request) as session:
        return series_list(session, q=q, material=material)


@router.get("/series/{series_key}")
def get_series(request: Request, series_key: SeriesKey) -> dict[str, Any]:
    with scope(request) as session:
        return series_detail(session, series_key)


@router.get("/units")
def search_units(
    request: Request,
    q: Annotated[str | None, Query(max_length=200)] = None,
    series: Annotated[str | None, Query(pattern=r"^[a-z0-9][a-z0-9-]{0,119}$")] = None,
    kind: UnitKind | None = None,
    material: MaterialClass | None = None,
    season: Annotated[int | None, Query(ge=0, le=100)] = None,
    episode: Annotated[int | None, Query(ge=0, le=100_000)] = None,
    chapter: Annotated[str | None, Query(pattern=r"^\d{1,6}(\.\d{1,3})?$")] = None,
    collection: Annotated[str | None, Query(max_length=120)] = None,
    creator: Annotated[str | None, Query(max_length=120)] = None,
    confidence: Confidence | None = None,
    root: Annotated[
        str | None, Query(pattern=r"^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$")
    ] = None,
    media_id: Annotated[str | None, Query(pattern=MEDIA_ID_PATTERN)] = None,
    include_duplicates: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> dict[str, Any]:
    relative: str | None = None
    if media_id is not None:
        try:
            relative = _media(request).describe(media_id).relative
        except MediaUnavailableError:
            raise HTTPException(status_code=404, detail={"message": "media not found"}) from None
    try:
        chapter_number = Decimal(chapter) if chapter is not None else None
    except InvalidOperation:
        raise HTTPException(status_code=422, detail={"message": "Not a chapter number."}) from None
    with scope(request) as session:
        return unit_search(
            session,
            q=q,
            series_key=series,
            kind=kind,
            material=material,
            season=season,
            episode=episode,
            chapter=chapter_number,
            collection=collection,
            creator=creator,
            confidence=confidence,
            root_key=root,
            vault_relative=relative,
            include_duplicates=include_duplicates or media_id is not None,
            limit=limit,
            offset=offset,
        )


@router.get("/units/{unit_id}")
def get_unit(request: Request, unit_id: uuid.UUID) -> dict[str, Any]:
    with scope(request) as session:
        return unit_detail(session, unit_id)


@router.get("/entries")
def list_entries(
    request: Request,
    root: Annotated[
        str | None, Query(pattern=r"^(source_vault|intake:[a-z0-9][a-z0-9-]{0,39})$")
    ] = None,
    status: EntryStatus | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> dict[str, Any]:
    with scope(request) as session:
        return entry_list(session, root_key=root, status=status, q=q, limit=limit, offset=offset)


@router.get("/search")
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, Any]:
    with scope(request) as session:
        return search_everything(session, q, projects=_projects(request), limit=limit)


# -- progress --------------------------------------------------------------------------
@router.post("/progress/reading")
def progress_reading(request: Request, body: ReadingIn) -> dict[str, Any]:
    with scope(request) as session:
        return record_reading(
            session, _media(request), body.media_id, body.page_index, project_key=body.project_key
        )


@router.post("/progress/watching")
def progress_watching(request: Request, body: WatchingIn) -> dict[str, Any]:
    with scope(request) as session:
        return record_watching(
            session,
            _media(request),
            media_id=body.media_id,
            member_id=body.member_id,
            position_ms=body.position_ms,
            duration_ms=body.duration_ms,
            ended=body.ended,
            project_key=body.project_key,
        )


@router.get("/progress/continue")
def progress_continue(
    request: Request,
    project: Annotated[str | None, Query(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
) -> list[dict[str, Any]]:
    with scope(request) as session:
        return continue_items(session, project_key=project, limit=limit)


@router.get("/progress/position")
def progress_position(
    request: Request,
    media_id: Annotated[str | None, Query(pattern=MEDIA_ID_PATTERN)] = None,
    member_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    if (media_id is None) == (member_id is None):
        raise HTTPException(status_code=422, detail={"message": "Give a media id or a member id."})
    with scope(request) as session:
        return {
            "position": position_for(
                session, media=_media(request), media_id=media_id, member_id=member_id
            )
        }


# -- videos inside archives ---------------------------------------------------------------
@router.get("/members/{member_id}")
def get_member(request: Request, member_id: uuid.UUID) -> dict[str, Any]:
    with scope(request) as session:
        return member_state(session, member_id, _cache(request))


@router.post("/members/{member_id}/prepare", status_code=202)
def prepare(request: Request, member_id: uuid.UUID) -> dict[str, Any]:
    """Queue the extraction of one archived video into the managed cache."""
    with scope(request) as session:
        return prepare_member(session, member_id, _cache(request))


@router.get("/members/{member_id}/content")
def member_content(request: Request, member_id: uuid.UUID) -> Response:
    """Stream a prepared archive member, honouring a single byte range."""
    cache = _cache(request)
    with scope(request) as session:
        member, _entry = member_record(session, member_id)
        sha = member.cached_sha256
        name = member.name
    if not sha or not cache.has(sha):
        raise HTTPException(status_code=409, detail={"message": "Prepare this video first."})
    extension = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    size = int(cache.size(sha) or 0)
    header = request.headers.get("range")
    start, end = 0, None
    if header:
        match = _RANGE.match(header.strip())
        if not match or (not match.group(1) and not match.group(2)):
            return Response(status_code=416)
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else None
        else:
            start = max(size - int(match.group(2)), 0)
    try:
        total, first, last, body = cache.open_range(sha, start, end)
    except ValueError:
        return Response(status_code=416)
    except OSError:
        raise HTTPException(
            status_code=409, detail={"message": "Prepare this video again."}
        ) from None
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(last - first + 1),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-transform",
    }
    code = 200
    if header:
        headers["Content-Range"] = f"bytes {first}-{last}/{total}"
        code = 206
    return StreamingResponse(
        body,
        status_code=code,
        media_type=MEMBER_TYPES.get(extension, "application/octet-stream"),
        headers=headers,
    )
