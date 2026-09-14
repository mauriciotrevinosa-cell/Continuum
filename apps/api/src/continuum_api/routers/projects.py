"""Projects: the creative work made inside Continuum, and its documents.

A project is data. Projects are discovered from configured sources - a
directory, or a Git ref read at its current commit - each described by its
own manifest; this router has no idea which projects exist until it asks, and
an installation with none answers with an empty list.

Lifecycle is explicit. A document is approved because its manifest says so,
directly or through a rule the manifest declares - never because of its
folder, or because a tool generated it. Unregistered documents are UNFILED.

The episode board is computed from the documents on every read: which
readiness level each episode reached is derived from what is committed, not
stored anywhere Continuum could let it drift.

Addresses are ids (project and document slugs) that only index manifests
already loaded; no route accepts a path (F-50), and documents are read
through the storage layer.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Annotated, Any

from continuum_storage import (
    PROJECT_ID_PATTERN,
    EpisodeStanding,
    Project,
    ProjectDocument,
    ProjectLibrary,
)
from fastapi import APIRouter, HTTPException, Request, status
from fastapi import Path as PathParam

from continuum_api.schemas import (
    DocumentOverride,
    EpisodeBoardSummary,
    EpisodeDocumentRef,
    EpisodeLevel,
    EpisodePageCount,
    EpisodeSource,
    EpisodeStandingOut,
    PageTotal,
    PipelineStage,
    ProjectDetail,
    ProjectDocumentBody,
    ProjectDocumentOut,
    ProjectResync,
    ProjectSource,
    ProjectSummary,
)

router = APIRouter(prefix="/projects", tags=["projects"])

ProjectId = Annotated[str, PathParam(pattern=PROJECT_ID_PATTERN)]
DocumentId = Annotated[str, PathParam(pattern=PROJECT_ID_PATTERN)]

CONTINUITY = frozenset({"APPROVED", "LOCKED"})
IN_PROGRESS = frozenset({"IDEA", "DRAFT", "REVIEW", "UNFILED"})
# Notes and references are kept with a project, never counted as its work.
EXTRA_SECTIONS = frozenset({"extra", "reference"})


def _library(request: Request) -> ProjectLibrary:
    library: ProjectLibrary = request.app.state.projects
    return library


def _iso(ns: int | None) -> str | None:
    if not ns:
        return None
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.UTC).isoformat(timespec="seconds")


def _version_key(version: str | None) -> list[int]:
    return [int(part) if part.isdigit() else 0 for part in (version or "0").split(".")]


def _source(project: Project) -> ProjectSource:
    raw: dict[str, Any] = project.source or {}
    if raw.get("kind") != "git":
        return ProjectSource(kind="directory")
    return ProjectSource(
        kind="git",
        ref=raw.get("ref"),
        directory=raw.get("directory"),
        commit=raw.get("commit"),
        committed_at=_iso(raw.get("committed_ns")),
        subject=raw.get("subject"),
    )


def _summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        title=project.title,
        kind=project.kind,
        logline=project.logline,
        status=project.status,
        documents=len(project.documents),
        approved=sum(1 for d in project.documents if d.lifecycle in CONTINUITY),
        in_progress=sum(
            1
            for d in project.documents
            if d.lifecycle in IN_PROGRESS
            and d.section not in EXTRA_SECTIONS
            and d.resolved_by is None
        ),
        extras=sum(
            1
            for d in project.documents
            if d.section in EXTRA_SECTIONS and d.lifecycle not in {"SUPERSEDED", "ARCHIVED"}
        ),
        updated_at=_iso(project.modified_ns),
        warnings=list(project.warnings),
        source=_source(project),
    )


def _document(document: ProjectDocument, project: Project) -> ProjectDocumentOut:
    superseded_by = next((d.id for d in project.documents if d.supersedes == document.id), None)
    return ProjectDocumentOut(
        id=document.id,
        title=document.title,
        category=document.category,
        section=document.section,  # type: ignore[arg-type]
        lifecycle=document.lifecycle,  # type: ignore[arg-type]
        version=document.version,
        lineage=document.lineage,
        supersedes=document.supersedes,
        superseded_by=superseded_by,
        derived_from=document.derived_from,
        episode=document.episode,
        summary=document.summary,
        author_status=document.author_status,
        dated=document.dated,
        modified_at=_iso(document.modified_ns),
        size_bytes=document.size_bytes,
        filed=document.filed,
        constraints=list(document.constraints),
        maturity=document.maturity,  # type: ignore[arg-type]
        authority=document.authority,  # type: ignore[arg-type]
        overrides=[DocumentOverride(document=d, scope=scope) for d, scope in document.overrides],
        overridden_by=[
            DocumentOverride(document=other.id, scope=scope)
            for other in project.documents
            for target, scope in other.overrides
            if target == document.id
        ],
        registration=document.registration,  # type: ignore[arg-type]
        convention=document.convention,
        facts=dict(document.facts),
        commit=document.commit,
        resolved_by=document.resolved_by,
        applies_to=document.applies_to,
    )


def _sources(project: Project, episode: EpisodeStanding) -> list[EpisodeSource]:
    by_id = {d.id: d for d in project.documents}
    labels = {role["role"]: role["label"] for role in project.source_roles}
    return [
        EpisodeSource(
            role=role,
            label=labels.get(role, role),
            document_id=doc_id,
            title=by_id[doc_id].title,
            lifecycle=by_id[doc_id].lifecycle,  # type: ignore[arg-type]
            commit=by_id[doc_id].commit,
            required=required,
            when=when,
        )
        for role, doc_id, required, when in episode.sources
        if doc_id in by_id
    ]


def _board(project: Project) -> tuple[list[EpisodeStandingOut], EpisodeBoardSummary]:
    by_id = {d.id: d for d in project.documents}
    counting = {level["id"] for level in project.levels if level.get("count_pages")}
    rows = []
    for episode in project.episodes:
        rows.append(
            EpisodeStandingOut(
                code=episode.code,
                season=episode.season,
                number=episode.number,
                title=episode.title,
                level=episode.level,
                label=episode.label,
                state=episode.state,
                pages=episode.pages,
                documents=[
                    EpisodeDocumentRef(
                        category=category,
                        id=doc_id,
                        title=by_id[doc_id].title,
                        lifecycle=by_id[doc_id].lifecycle,  # type: ignore[arg-type]
                        resolved_by=by_id[doc_id].resolved_by,
                    )
                    for category, doc_id in episode.documents
                    if doc_id in by_id
                ],
                missing=list(episode.missing),
                last_commit=episode.last_commit,
                last_changed_at=_iso(episode.last_changed_ns),
                page_counts=[
                    EpisodePageCount(id=cid, label=label, pages=pages, document_id=doc)
                    for cid, label, pages, doc in episode.page_counts
                ],
                current_count=episode.current_count,
                sources=_sources(project, episode),
                missing_sources=list(episode.missing_sources),
            )
        )
    summary = EpisodeBoardSummary(
        episodes=len(rows),
        by_level=dict(Counter(r.level for r in rows if r.level is not None)),
        pages=sum(r.pages or 0 for r in rows if r.level in counting),
        unmet=sum(1 for r in rows if r.level is None),
        page_totals=[PageTotal(**total) for total in project.page_totals],
    )
    return rows, summary


@router.get("", response_model=list[ProjectSummary])
def list_projects(request: Request) -> list[ProjectSummary]:
    projects = sorted(_library(request).projects(), key=lambda p: p.title.lower())
    return [_summary(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectDetail)
def project_detail(request: Request, project_id: ProjectId) -> ProjectDetail:
    project = _library(request).project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    by_category = Counter(
        d.category for d in project.documents if d.lifecycle not in {"SUPERSEDED", "ARCHIVED"}
    )
    episodes, summary = _board(project)
    return ProjectDetail(
        project=_summary(project),
        description=project.description,
        documents=[_document(d, project) for d in project.documents],
        pipeline=[
            PipelineStage(
                id=str(stage["id"]),
                title=str(stage["title"]),
                track=str(stage["track"]),
                description=str(stage["description"]),
                artifacts=by_category.get(str(stage["id"]), 0),
            )
            for stage in project.pipeline
        ],
        counts=dict(Counter(d.lifecycle for d in project.documents)),
        levels=[EpisodeLevel(**level) for level in project.levels],
        episodes=episodes,
        episode_summary=summary,
    )


@router.post("/{project_id}/resync", response_model=ProjectResync)
def resync_project(request: Request, project_id: ProjectId) -> ProjectResync:
    """Bring the project up to date with its source.

    For a project read from a remote-tracking Git ref this fetches that ref
    (nothing else in the repository changes); the project is then re-read at
    the commit the ref now points to. A failed fetch is reported, not raised.
    """
    library = _library(request)
    result = library.resync(project_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    project = library.project(project_id)
    return ProjectResync(
        project_id=project_id,
        fetched=result.fetched,
        previous_commit=result.previous_commit,
        commit=result.commit,
        changed=result.previous_commit != result.commit,
        detail=result.detail,
        source=_source(project) if project is not None else ProjectSource(),
    )


@router.get(
    "/{project_id}/episodes/{episode}/production-sources", response_model=list[EpisodeSource]
)
def episode_production_sources(
    request: Request,
    project_id: ProjectId,
    episode: Annotated[str, PathParam(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")],
) -> list[EpisodeSource]:
    """The documents a chapter package for this episode is built from, in order.

    Resolved from the committed documents by the roles the project manifest
    declares (the episode's own scripts, season overlays, project bibles and
    addenda); nothing is registered per episode.
    """
    project = _library(request).project(project_id)
    found = next((e for e in project.episodes if e.code == episode), None) if project else None
    if project is None or found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="episode not found")
    return _sources(project, found)


@router.get("/{project_id}/documents/{document_id}", response_model=ProjectDocumentBody)
def project_document(
    request: Request, project_id: ProjectId, document_id: DocumentId
) -> ProjectDocumentBody:
    found = _library(request).document(project_id, document_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    project, document, markdown = found
    versions = [
        _document(d, project)
        for d in project.documents
        if document.lineage and d.lineage == document.lineage
    ]
    versions.sort(key=lambda d: _version_key(d.version))
    return ProjectDocumentBody(
        project=_summary(project),
        document=_document(document, project),
        markdown=markdown,
        versions=versions,
    )
