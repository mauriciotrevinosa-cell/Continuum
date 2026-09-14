"""Projects: the creative work made inside Continuum, and its documents.

A project is data. Projects are discovered from configured source
directories, each described by its own manifest; this router has no idea
which projects exist until it asks, and an installation with none answers
with an empty list.

Lifecycle is explicit. A document is approved because its manifest says so -
never because of its folder, its file name, its author's prose, or because a
tool generated it. Unregistered documents are shown as UNFILED.

Addresses are ids (project and document slugs) that only index manifests
already loaded; no route accepts a path (F-50), and documents are read
through the storage layer's contained resolver.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Annotated

from continuum_storage import PROJECT_ID_PATTERN, Project, ProjectDocument, ProjectLibrary
from fastapi import APIRouter, HTTPException, Request, status
from fastapi import Path as PathParam

from continuum_api.schemas import (
    DocumentOverride,
    PipelineStage,
    ProjectDetail,
    ProjectDocumentBody,
    ProjectDocumentOut,
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


def _iso(ns: int) -> str | None:
    if not ns:
        return None
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.UTC).isoformat(timespec="seconds")


def _version_key(version: str | None) -> list[int]:
    return [int(part) if part.isdigit() else 0 for part in (version or "0").split(".")]


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
            if d.lifecycle in IN_PROGRESS and d.section not in EXTRA_SECTIONS
        ),
        extras=sum(
            1
            for d in project.documents
            if d.section in EXTRA_SECTIONS and d.lifecycle not in {"SUPERSEDED", "ARCHIVED"}
        ),
        updated_at=_iso(project.modified_ns),
        warnings=list(project.warnings),
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
    )


@router.get("", response_model=list[ProjectSummary])
def list_projects(request: Request) -> list[ProjectSummary]:
    projects = sorted(_library(request).projects(), key=lambda p: p.title.lower())
    return [_summary(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectDetail)
def project_detail(request: Request, project_id: ProjectId) -> ProjectDetail:
    project = _library(request).project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    by_category = Counter(d.category for d in project.documents)
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
    )


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
