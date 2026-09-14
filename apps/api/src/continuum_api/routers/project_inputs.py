"""Project production inputs: reference manifests, chapter packages, music references.

Every route addresses records by id or key (F-50). Manifests are resolved from
the catalog and the reference vault read-only; chapter packages are validated
and stored as new versions, never overwritten; music references are metadata
only - a link is stored and never fetched.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from continuum_core.catalog import ApprovalState
from continuum_production import (
    ChapterPackages,
    ManifestRequest,
    MusicReferences,
    ReferenceManifests,
    SourceMoment,
    SourcePage,
    manifest_view,
    music_view,
    package_json_schema,
    package_view,
)
from continuum_storage import ProjectLibrary
from fastapi import APIRouter, HTTPException, Request
from fastapi import Path as PathParam
from pydantic import Field

from continuum_api.routers.library import StrictBody, catalog_scope

router = APIRouter(tags=["project-inputs"])

ProjectId = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]
PackageKey = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,119}$")]


def _projects(request: Request) -> ProjectLibrary:
    library: ProjectLibrary = request.app.state.projects
    return library


def _known(request: Request, project_id: str) -> None:
    if _projects(request).project(project_id) is None:
        raise HTTPException(status_code=404, detail={"message": "That project is not discovered."})


# -- reference manifests ------------------------------------------------------------
class SourcePageIn(StrictBody):
    unit_id: uuid.UUID
    page: int = Field(ge=1, le=100_000)
    note: str = Field(default="", max_length=400)


class SourceMomentIn(StrictBody):
    unit_id: uuid.UUID
    time_ms: int = Field(ge=0, le=100 * 3600 * 1000)
    note: str = Field(default="", max_length=400)


class ChapterPackageRefIn(StrictBody):
    package_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,119}$")
    version: int = Field(ge=1)


class ManifestIn(StrictBody):
    label: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=400)
    character_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    reference_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    include_project_references: bool = False
    source_pages: list[SourcePageIn] = Field(default_factory=list, max_length=300)
    source_moments: list[SourceMomentIn] = Field(default_factory=list, max_length=300)
    document_ids: list[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]] = Field(
        default_factory=list, max_length=100
    )
    music_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    chapter_package: ChapterPackageRefIn | None = None
    generation_settings: dict[str, Any] = Field(default_factory=dict)


@router.post("/projects/{project_id}/reference-manifests", status_code=201)
def build_manifest(request: Request, project_id: ProjectId, body: ManifestIn) -> dict[str, Any]:
    """Resolve a deterministic production input manifest from the real Vault."""
    _known(request, project_id)
    with catalog_scope(request) as catalog:
        manifests = ReferenceManifests(catalog.session, catalog, projects=_projects(request))
        row = manifests.build(
            ManifestRequest(
                project_key=project_id,
                label=body.label,
                purpose=body.purpose,
                character_ids=tuple(body.character_ids),
                reference_ids=tuple(body.reference_ids),
                include_project_references=body.include_project_references,
                source_pages=tuple(
                    SourcePage(p.unit_id, p.page, p.note) for p in body.source_pages
                ),
                source_moments=tuple(
                    SourceMoment(m.unit_id, m.time_ms, m.note) for m in body.source_moments
                ),
                document_ids=tuple(body.document_ids),
                music_ids=tuple(body.music_ids),
                chapter_package=(body.chapter_package.package_key, body.chapter_package.version)
                if body.chapter_package
                else None,
                generation_settings=body.generation_settings,
            )
        )
        return manifest_view(row)


@router.get("/projects/{project_id}/reference-manifests")
def list_manifests(request: Request, project_id: ProjectId) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        manifests = ReferenceManifests(catalog.session, catalog, projects=_projects(request))
        return [manifest_view(row, full=False) for row in manifests.for_project(project_id)]


@router.get("/production/reference-manifests/{manifest_id}")
def get_manifest(request: Request, manifest_id: uuid.UUID) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        return manifest_view(ReferenceManifests(catalog.session, catalog).get(manifest_id))


# -- chapter packages ----------------------------------------------------------------
class PackageIn(StrictBody):
    body: dict[str, Any]
    notes: str = Field(default="", max_length=4000)


class ValidateIn(StrictBody):
    body: dict[str, Any]


class ApprovalIn(StrictBody):
    version: int = Field(ge=1)
    approval_state: ApprovalState
    row_version: int = Field(ge=1)


@router.get("/production/chapter-package-schema")
def chapter_package_schema() -> dict[str, Any]:
    return package_json_schema()


@router.post("/projects/{project_id}/chapter-packages/validate")
def validate_package(request: Request, project_id: ProjectId, body: ValidateIn) -> dict[str, Any]:
    parsed, problems = ChapterPackages.validate(project_id, body.body)
    return {"valid": parsed is not None, "problems": problems}


@router.get("/projects/{project_id}/chapter-packages")
def list_packages(request: Request, project_id: ProjectId) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        return [
            package_view(row, full=False)
            for row in ChapterPackages(catalog.session).for_project(project_id)
        ]


@router.post("/projects/{project_id}/chapter-packages/{package_key}", status_code=201)
def save_package(
    request: Request, project_id: ProjectId, package_key: PackageKey, body: PackageIn
) -> dict[str, Any]:
    _known(request, project_id)
    with catalog_scope(request) as catalog:
        row = ChapterPackages(catalog.session).save(
            project_id, package_key, body.body, notes=body.notes
        )
        return package_view(row)


@router.get("/projects/{project_id}/chapter-packages/{package_key}")
def package_versions(
    request: Request, project_id: ProjectId, package_key: PackageKey
) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        return [
            package_view(row)
            for row in ChapterPackages(catalog.session).versions(project_id, package_key)
        ]


@router.post("/projects/{project_id}/chapter-packages/{package_key}/approval")
def package_approval(
    request: Request, project_id: ProjectId, package_key: PackageKey, body: ApprovalIn
) -> dict[str, Any]:
    with catalog_scope(request) as catalog:
        row = ChapterPackages(catalog.session).set_approval(
            project_id, package_key, body.version, body.approval_state, body.row_version
        )
        return package_view(row)


# -- music references ----------------------------------------------------------------
class MusicIn(StrictBody):
    track: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="", max_length=300)
    reference: str = Field(default="", max_length=2000)
    episode: str = Field(default="", max_length=40)
    scene: str = Field(default="", max_length=200)
    mood: str = Field(default="", max_length=200)
    intended_use: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=8000)


class MusicUpdateIn(StrictBody):
    row_version: int = Field(ge=1)
    track: str | None = Field(default=None, max_length=300)
    artist: str | None = Field(default=None, max_length=300)
    reference: str | None = Field(default=None, max_length=2000)
    episode: str | None = Field(default=None, max_length=40)
    scene: str | None = Field(default=None, max_length=200)
    mood: str | None = Field(default=None, max_length=200)
    intended_use: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=8000)


class RowVersionIn(StrictBody):
    row_version: int = Field(ge=1)


@router.get("/projects/{project_id}/music")
def list_music(request: Request, project_id: ProjectId) -> list[dict[str, Any]]:
    with catalog_scope(request) as catalog:
        return [music_view(row) for row in MusicReferences(catalog.session).list(project_id)]


@router.post("/projects/{project_id}/music", status_code=201)
def add_music(request: Request, project_id: ProjectId, body: MusicIn) -> dict[str, Any]:
    _known(request, project_id)
    with catalog_scope(request) as catalog:
        return music_view(MusicReferences(catalog.session).add(project_id, **body.model_dump()))


@router.post("/projects/{project_id}/music/{music_id}/update")
def update_music(
    request: Request, project_id: ProjectId, music_id: uuid.UUID, body: MusicUpdateIn
) -> dict[str, Any]:
    changes = body.model_dump(exclude_none=True)
    row_version = changes.pop("row_version")
    with catalog_scope(request) as catalog:
        row = MusicReferences(catalog.session).update(project_id, music_id, row_version, **changes)
        return music_view(row)


@router.post("/projects/{project_id}/music/{music_id}/remove", status_code=204)
def remove_music(
    request: Request, project_id: ProjectId, music_id: uuid.UUID, body: RowVersionIn
) -> None:
    with catalog_scope(request) as catalog:
        MusicReferences(catalog.session).remove(project_id, music_id, body.row_version)
