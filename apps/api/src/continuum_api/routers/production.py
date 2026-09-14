"""Rough manga production routes: artifacts, attempts, review, provenance.

The API records recipes and **enqueues**; the worker renders (ADR-0002). Every
route addresses records by id (F-50). A panel-script document is named by its
manifest id and its version is read from the manifest, never taken from the
client. Images are served from ``generated/`` by attempt id and kind.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from continuum_core.references import (
    BundleRole,
    CharacterAspect,
    DerivativeKind,
    EditOperationKind,
    ReviewDecision,
    RoughMode,
    RoughPurpose,
)
from continuum_library import CharacterLink, ReferenceCatalog, reference_view
from continuum_production import (
    BundleEntry,
    CharacterDirection,
    EditOperation,
    Placement,
    RoughIntentSpec,
    RoughProduction,
    artifact_view,
    attempt_view,
    character_manifest,
    completion_view,
    provenance_view,
)
from continuum_providers import Capability, DataClass, ProviderRegistry
from continuum_storage import ProjectLibrary
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi import Path as PathParam
from pydantic import Field
from starlette.responses import Response

from continuum_api.routers.library import CharacterLinkIn, RegionIn, StrictBody, catalog_scope

router = APIRouter(tags=["production"])

ProjectId = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]


@contextmanager
def production_scope(request: Request) -> Iterator[RoughProduction]:
    providers: ProviderRegistry = request.app.state.providers
    with catalog_scope(request) as catalog:
        yield RoughProduction(catalog.session, catalog, providers=providers)


def _projects(request: Request) -> ProjectLibrary:
    library: ProjectLibrary = request.app.state.projects
    return library


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class ArtifactIn(StrictBody):
    episode: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
    page: int = Field(ge=1, le=10_000)
    panel: int | None = Field(default=None, ge=1, le=100)
    chapter: int | None = Field(default=None, ge=1, le=10_000)
    title: str = ""
    brief: str = ""
    panel_script_document: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    #: PRODUCTION (a real page), WORKFLOW_TEST or NON_CANON_SAMPLE. Tests and
    #: samples never count as manga and can never be creatively approved.
    purpose: RoughPurpose = RoughPurpose.PRODUCTION


class BundleEntryIn(StrictBody):
    role: BundleRole
    reference_id: uuid.UUID
    character_id: uuid.UUID | None = None
    outfit_id: uuid.UUID | None = None
    aspect: CharacterAspect | None = None
    label: str = ""
    region: RegionIn | None = None


class OperationIn(StrictBody):
    kind: EditOperationKind
    region: RegionIn
    label: str = ""
    character_id: uuid.UUID | None = None
    outfit_id: uuid.UUID | None = None
    reference_position: int | None = None
    text: str = ""
    notes: str = ""


class PlacementIn(StrictBody):
    region: RegionIn
    label: str = ""
    character_id: uuid.UUID | None = None


class DirectionIn(StrictBody):
    character_id: uuid.UUID
    outfit_id: uuid.UUID | None = None
    acting_direction: str = ""
    visual_mode_id: uuid.UUID | None = None


class ExecutionIn(StrictBody):
    strength: float | None = Field(default=None, ge=0, le=1)
    inpaint: dict[str, Any] = Field(default_factory=dict)
    control_inputs: list[dict[str, Any]] = Field(default_factory=list)
    compositing: dict[str, Any] = Field(default_factory=dict)
    post_processing: list[str] = Field(default_factory=list)


class AttemptIn(StrictBody):
    mode: RoughMode
    bundle: list[BundleEntryIn] = Field(default_factory=list, max_length=24)
    characters: list[DirectionIn] = Field(default_factory=list, max_length=12)
    visual_mode_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    operations: list[OperationIn] = Field(default_factory=list, max_length=32)
    placements: list[PlacementIn] = Field(default_factory=list, max_length=16)
    plate_region: RegionIn | None = None
    brief: str = ""
    width: int | None = None
    height: int | None = None
    seed: int | None = None
    execution: ExecutionIn = Field(default_factory=ExecutionIn)

    def spec(self) -> RoughIntentSpec:
        extra = {k: v for k, v in self.execution.model_dump().items() if v not in (None, {}, [])}
        return RoughIntentSpec(
            mode=self.mode,
            bundle=tuple(
                BundleEntry(
                    role=b.role,
                    reference_id=b.reference_id,
                    character_id=b.character_id,
                    outfit_id=b.outfit_id,
                    aspect=b.aspect,
                    label=b.label,
                    region=b.region.region() if b.region else None,
                )
                for b in self.bundle
            ),
            characters=tuple(CharacterDirection(**c.model_dump()) for c in self.characters),
            visual_mode_ids=tuple(self.visual_mode_ids),
            operations=tuple(
                EditOperation(
                    kind=o.kind,
                    region=o.region.region(),
                    label=o.label,
                    character_id=o.character_id,
                    outfit_id=o.outfit_id,
                    reference_position=o.reference_position,
                    text=o.text,
                    notes=o.notes,
                )
                for o in self.operations
            ),
            placements=tuple(
                Placement(region=p.region.region(), label=p.label, character_id=p.character_id)
                for p in self.placements
            ),
            plate_region=self.plate_region.region() if self.plate_region else None,
            brief=self.brief,
            width=self.width,
            height=self.height,
            seed=self.seed,
            extra_execution=extra,
        )


class ReviewIn(StrictBody):
    decision: ReviewDecision
    notes: str = ""
    seed: int | None = None


class ContinuityIn(StrictBody):
    label: str = ""
    notes: str = ""
    characters: list[CharacterLinkIn] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.get("/production/readiness")
def readiness(request: Request) -> dict[str, Any]:
    """Whether a rough renderer is permitted, and which - without running it."""
    providers: ProviderRegistry = request.app.state.providers
    decision = providers.evaluate(Capability.ROUGH_RENDER, DataClass.SOURCE_EXCERPT)
    descriptor = providers.get(decision.provider_id).descriptor if decision.provider_id else None
    return {
        "permitted": decision.permitted,
        "provider_id": decision.provider_id,
        "is_fake": bool(descriptor and descriptor.id.startswith("fake.")),
        "license_note": descriptor.license_note if descriptor else None,
        "blocked_reason": decision.blocked_reason.value if decision.blocked_reason else None,
        "remediation": decision.remediation,
    }


@router.get("/projects/{project_id}/rough-artifacts")
def list_artifacts(
    request: Request,
    project_id: ProjectId,
    episode: str | None = None,
    purpose: RoughPurpose | None = None,
) -> list[dict[str, Any]]:
    with production_scope(request) as production:
        return [
            artifact_view(production, a)
            for a in production.artifacts(project_id, episode=episode, purpose=purpose)
        ]


@router.get("/projects/{project_id}/characters/{character_id}/manifest")
def get_character_manifest(
    request: Request, project_id: ProjectId, character_id: uuid.UUID
) -> dict[str, Any]:
    """Every reference that can ground this character in this project, by facet and lane."""
    if _projects(request).project(project_id) is None:
        raise HTTPException(status_code=404, detail={"message": "project not found"})
    with catalog_scope(request) as catalog:
        return character_manifest(
            catalog.session,
            catalog,
            character_id,
            project_key=project_id,
            projects=_projects(request),
        )


@router.get("/projects/{project_id}/rough-completion")
def rough_completion(request: Request, project_id: ProjectId) -> dict[str, Any]:
    """Rough manga completion, counting production work only; tests are listed apart."""
    with production_scope(request) as production:
        return completion_view(production, project_id)


@router.post("/projects/{project_id}/rough-artifacts", status_code=201)
def create_artifact(request: Request, project_id: ProjectId, body: ArtifactIn) -> dict[str, Any]:
    project = _projects(request).project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"message": "project not found"})
    version = None
    if body.panel_script_document is not None:
        document = next((d for d in project.documents if d.id == body.panel_script_document), None)
        if document is None:
            raise HTTPException(status_code=404, detail={"message": "panel script not found"})
        version = document.version
    with production_scope(request) as production:
        artifact = production.create_artifact(
            project_id,
            body.episode,
            body.page,
            panel=body.panel,
            chapter=body.chapter,
            title=body.title,
            brief=body.brief,
            panel_script_document=body.panel_script_document,
            panel_script_version=version,
            purpose=body.purpose,
        )
        return artifact_view(production, artifact)


@router.get("/production/rough-artifacts/{artifact_id}")
def get_artifact(request: Request, artifact_id: uuid.UUID) -> dict[str, Any]:
    with production_scope(request) as production:
        artifact = production.artifact(artifact_id)
        catalog: ReferenceCatalog = production.catalog
        view = artifact_view(production, artifact)
        view["scene_sources"] = [
            {
                "id": str(row.id),
                "panel": row.panel,
                "role": row.role.value,
                "notes": row.notes,
                "reference": reference_view(
                    catalog, catalog.reference(row.reference_id), with_source=False
                ),
            }
            for row in catalog.panel_sources(
                artifact.project_key, episode=artifact.episode, page=artifact.page
            )
        ]
        view["modes_in_effect"] = [
            {
                "assignment_id": str(a.id),
                "visual_mode_id": str(a.visual_mode_id),
                "name": catalog.visual_mode(a.visual_mode_id).name,
                "scope": a.scope.value,
                "trigger": a.trigger.value,
                "character_id": str(a.character_id) if a.character_id else None,
            }
            for a in catalog.modes_in_effect(
                artifact.project_key, artifact.episode, artifact.page, artifact.panel
            )
        ]
        return view


@router.post("/production/rough-artifacts/{artifact_id}/attempts", status_code=202)
def request_attempt(request: Request, artifact_id: uuid.UUID, body: AttemptIn) -> dict[str, Any]:
    with production_scope(request) as production:
        attempt = production.request_attempt(artifact_id, body.spec())
        return attempt_view(production, attempt)


@router.get("/production/attempts/{attempt_id}")
def get_attempt(request: Request, attempt_id: uuid.UUID) -> dict[str, Any]:
    with production_scope(request) as production:
        return attempt_view(production, production.attempt(attempt_id))


@router.get("/production/attempts/{attempt_id}/provenance")
def get_provenance(request: Request, attempt_id: uuid.UUID) -> dict[str, Any]:
    with production_scope(request) as production:
        return provenance_view(production, production.attempt(attempt_id))


@router.get("/production/attempts/{attempt_id}/image")
def attempt_image(
    request: Request,
    attempt_id: uuid.UUID,
    kind: Annotated[DerivativeKind, Query()] = DerivativeKind.OUTPUT,
) -> Response:
    with production_scope(request) as production:
        data, mime = production.derivative_bytes(attempt_id, kind)
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/production/attempts/{attempt_id}/review")
def review_attempt(request: Request, attempt_id: uuid.UUID, body: ReviewIn) -> dict[str, Any]:
    with production_scope(request) as production:
        _review, new = production.review(
            attempt_id, body.decision, notes=body.notes, seed=body.seed
        )
        return {
            "attempt": attempt_view(production, production.attempt(attempt_id)),
            "regenerated": attempt_view(production, new) if new is not None else None,
        }


@router.post("/production/attempts/{attempt_id}/continuity", status_code=201)
def promote_to_continuity(
    request: Request, attempt_id: uuid.UUID, body: ContinuityIn
) -> dict[str, Any]:
    with production_scope(request) as production:
        item = production.promote_to_continuity(
            attempt_id,
            label=body.label,
            notes=body.notes,
            characters=tuple(CharacterLink(**c.model_dump()) for c in body.characters),
        )
        return reference_view(production.catalog, item)
