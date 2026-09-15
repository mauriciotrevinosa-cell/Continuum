"""Character reference corpus routes (M3): overview, observations, review, refresh.

Characters and observations are addressed by id (F-50). Images are served by
observation id: a curated reference's preview, or a source page read through
the read-only storage layer. Nothing here writes to the Source Vault.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from continuum_core.corpus import (
    Framing,
    ModelSheetKind,
    ObservationAuthority,
    ObservationFacet,
    ObservationRole,
    ObservationSource,
    ObservationStatus,
    ProductionEvidenceRole,
    ViewAngle,
    VisualOrigin,
)
from continuum_db.models import CharacterModelSheetAttempt, Job
from continuum_imaging.manga import analyze_layout
from continuum_library import CatalogNotFoundError
from continuum_production.character_models import CharacterModels
from continuum_production.corpus import CharacterCorpus, observation_view
from continuum_production.manga import source_page_reader
from continuum_production.model_builder import CharacterModelBuilder, attempt_view
from fastapi import APIRouter, Query, Request
from pydantic import Field
from starlette.responses import Response

from continuum_api.routers.library import StrictBody, catalog_scope

router = APIRouter(tags=["character-corpus"])


@contextmanager
def corpus_scope(request: Request) -> Iterator[CharacterCorpus]:
    with catalog_scope(request) as catalog:
        yield CharacterCorpus(
            catalog.session,
            catalog,
            page_reader=source_page_reader(catalog),
            analyze=analyze_layout,
        )


class RefreshIn(StrictBody):
    per_chapter: int = Field(default=2, ge=1, le=6)
    max_source_pages: int = Field(default=600, ge=0, le=5000)
    #: Pages whose layout is measured for framing hints in this call (reads pages).
    analyze_limit: int = Field(default=0, ge=0, le=300)


class ReviewIn(StrictBody):
    status: ObservationStatus | None = None
    role: ObservationRole | None = None
    authority: ObservationAuthority | None = None
    facets: list[ObservationFacet] | None = Field(default=None, max_length=8)
    angle: ViewAngle | None = None
    clear_angle: bool = False
    framing: Framing | None = None
    clear_framing: bool = False
    expression: str | None = Field(default=None, max_length=80)
    pose: str | None = Field(default=None, max_length=80)
    atypical: bool | None = None
    anchor: bool | None = None
    notes: str | None = Field(default=None, max_length=4000)

    def changes(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            key: value
            for key, value in self.model_dump(exclude={"clear_angle", "clear_framing"}).items()
            if value is not None
        }
        if self.clear_angle:
            out["angle"] = None
        if self.clear_framing:
            out["framing"] = None
        return out


class VisualOriginIn(StrictBody):
    visual_origin: VisualOrigin | None


class EnvironmentIn(StrictBody):
    tags: list[str] = Field(min_length=1, max_length=8)


class ProductionModelIn(StrictBody):
    project_key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4000)
    identity_rules: list[str] = Field(default_factory=list, max_length=40)
    restrictions: list[str] = Field(default_factory=list, max_length=40)
    active_outfit_id: uuid.UUID | None = None
    head_sheet_reference_id: uuid.UUID | None = None
    body_sheet_reference_id: uuid.UUID | None = None
    created_from: dict[str, Any] = Field(default_factory=dict)


class ProductionEvidenceIn(StrictBody):
    observation_id: uuid.UUID
    role: ProductionEvidenceRole
    preferred: bool = False
    required: bool = False
    position: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=2000)


class ApprovalIn(StrictBody):
    reviewer: str = Field(min_length=1, max_length=200)


class ModelSheetBuildIn(StrictBody):
    model_id: uuid.UUID
    sheet_kind: ModelSheetKind
    seed: int = Field(default=1, ge=0, le=2_147_483_647)


class ModelSheetReviewIn(StrictBody):
    decision: str = Field(pattern="^(APPROVE|REJECT|REGENERATE)$")
    reviewer: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=4000)


@router.get("/library/characters/{character_id}/overview")
def character_overview(request: Request, character_id: uuid.UUID) -> dict[str, Any]:
    """Who the character is, what they should look like, how well grounded, and on what."""
    with corpus_scope(request) as corpus:
        corpus.sync_curated(character_id)
        result = corpus.overview(character_id)
        models = CharacterModels(corpus.session)
        result["production_models"] = models.list(None, character_id)
        return result


@router.get("/library/characters/{character_id}/production-models")
def list_production_models(
    request: Request, character_id: uuid.UUID, project_key: str
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        models = CharacterModels(corpus.session)
        rows = models.list(project_key, character_id)
        active = models.active(project_key, character_id)
        return {"models": rows, "active_id": str(active.id) if active else None}


@router.post("/library/characters/{character_id}/production-models", status_code=201)
def create_production_model(
    request: Request, character_id: uuid.UUID, body: ProductionModelIn
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        models = CharacterModels(corpus.session)
        row = models.create(character_id=character_id, **body.model_dump())
        return models.view(row)


@router.post("/library/character-production-models/{model_id}/evidence", status_code=201)
def add_production_evidence(
    request: Request, model_id: uuid.UUID, body: ProductionEvidenceIn
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        models = CharacterModels(corpus.session)
        models.add_evidence(model_id, **body.model_dump())
        return models.view(models._model(model_id))


@router.post("/library/character-production-models/{model_id}/submit")
def submit_production_model(request: Request, model_id: uuid.UUID) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        models = CharacterModels(corpus.session)
        return models.view(models.submit(model_id))


@router.post("/library/character-production-models/{model_id}/approve")
def approve_production_model(
    request: Request, model_id: uuid.UUID, body: ApprovalIn
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        models = CharacterModels(corpus.session)
        return models.view(models.approve(model_id, body.reviewer))


def _builder(request: Request, corpus: CharacterCorpus) -> CharacterModelBuilder:
    return CharacterModelBuilder(
        corpus.session, corpus.catalog, request.app.state.providers, corpus
    )


@router.get("/library/characters/{character_id}/model-builder")
def model_builder_status(
    request: Request, character_id: uuid.UUID, project_key: str
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        builder = _builder(request, corpus)
        return {
            "readiness": builder.readiness(),
            "attempts": builder.attempts(project_key, character_id),
        }


@router.post("/library/character-model-sheet-attempts", status_code=202)
def build_model_sheet(request: Request, body: ModelSheetBuildIn) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        builder = _builder(request, corpus)
        row = builder.request(body.model_id, body.sheet_kind, seed=body.seed)
        return attempt_view(row, corpus.session.get(Job, row.job_id) if row.job_id else None)


@router.post("/library/character-model-sheet-attempts/{attempt_id}/review")
def review_model_sheet(
    request: Request, attempt_id: uuid.UUID, body: ModelSheetReviewIn
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        builder = _builder(request, corpus)
        row, model, regenerated = builder.review(
            attempt_id, body.decision, body.reviewer, body.notes
        )
        return {
            "attempt": attempt_view(
                row, corpus.session.get(Job, row.job_id) if row.job_id else None
            ),
            "new_production_model": CharacterModels(corpus.session).view(model) if model else None,
            "regenerated": attempt_view(
                regenerated,
                corpus.session.get(Job, regenerated.job_id) if regenerated.job_id else None,
            )
            if regenerated
            else None,
        }


@router.get("/library/character-model-sheet-attempts/{attempt_id}/image")
def model_sheet_image(request: Request, attempt_id: uuid.UUID) -> Response:
    with corpus_scope(request) as corpus:
        row = corpus.session.get(CharacterModelSheetAttempt, attempt_id)
        if row is None or row.reference_id is None:
            raise CatalogNotFoundError("That model-sheet image does not exist.")
        image = corpus.catalog.reference_image(row.reference_id)
    return Response(content=image.data, media_type=image.mime)


@router.get("/library/characters/{character_id}/observations")
def list_observations(
    request: Request,
    character_id: uuid.UUID,
    status: ObservationStatus | None = None,
    authority: ObservationAuthority | None = None,
    source_kind: ObservationSource | None = None,
    facet: ObservationFacet | None = None,
    angle: ViewAngle | None = None,
    expression: Annotated[str | None, Query(max_length=80)] = None,
    pose: Annotated[str | None, Query(max_length=80)] = None,
    with_character: Annotated[str | None, Query(max_length=200)] = None,
    ranked: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 60,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> dict[str, Any]:
    """Browse the corpus, or rank it for a need (``ranked=true``)."""
    with corpus_scope(request) as corpus:
        corpus.sync_curated(character_id)
        if ranked:
            need = {
                "facets": [facet.value] if facet else [],
                "angles": [angle.value] if angle else [],
                "expressions": [expression.lower()] if expression else [],
                "poses": [pose.lower()] if pose else [],
                "framing": None,
                "with": [with_character] if with_character else [],
            }
            found = corpus.retrieve(
                character_id, need, limit=limit, include_candidates=True, include_supplemental=True
            )
            return {"total": found["available"], **found}
        rows = corpus.observations(character_id)
        if status:
            rows = [r for r in rows if r.status == status.value]
        if authority:
            rows = [r for r in rows if r.authority == authority.value]
        if source_kind:
            rows = [r for r in rows if r.source_kind == source_kind.value]
        if facet:
            rows = [r for r in rows if facet.value in (r.facets or [])]
        if angle:
            rows = [r for r in rows if r.angle == angle.value]
        if expression:
            rows = [r for r in rows if r.expression == expression.lower()]
        if pose:
            rows = [r for r in rows if r.pose == pose.lower()]
        rows.sort(key=lambda r: (r.status != "CONFIRMED", not r.anchor, r.source_label, r.locator))
        return {
            "total": len(rows),
            "observations": [observation_view(r) for r in rows[offset : offset + limit]],
            "counts": corpus.counts(character_id),
        }


@router.post("/library/characters/{character_id}/corpus/refresh")
def refresh_corpus(request: Request, character_id: uuid.UUID, body: RefreshIn) -> dict[str, Any]:
    """Sync curated references and sweep the catalogued source for candidates."""
    with corpus_scope(request) as corpus:
        return corpus.refresh(
            character_id,
            per_chapter=body.per_chapter,
            max_source_pages=body.max_source_pages,
            analyze_limit=body.analyze_limit,
        )


@router.post("/library/character-observations/{observation_id}/review")
def review_observation(
    request: Request, observation_id: uuid.UUID, body: ReviewIn
) -> dict[str, Any]:
    with corpus_scope(request) as corpus:
        return observation_view(corpus.review(observation_id, body.changes()))


@router.post("/library/character-observations/{observation_id}/visual-origin")
def set_visual_origin(
    request: Request, observation_id: uuid.UUID, body: VisualOriginIn
) -> dict[str, Any]:
    """Who made the image - kept apart from where it was acquired."""
    with corpus_scope(request) as corpus:
        value = body.visual_origin.value if body.visual_origin else None
        return observation_view(corpus.set_visual_origin(observation_id, value))


@router.post("/library/character-observations/{observation_id}/environment", status_code=201)
def use_as_environment(
    request: Request, observation_id: uuid.UUID, body: EnvironmentIn
) -> dict[str, Any]:
    """Use the observed page as an environment reference with setting tags."""
    with corpus_scope(request) as corpus:
        item = corpus.tag_environment(observation_id, body.tags)
        return {"reference_id": str(item.id), "label": item.label, "tags": body.tags}


@router.get("/library/character-observations/{observation_id}/image")
def observation_image(request: Request, observation_id: uuid.UUID) -> Response:
    with corpus_scope(request) as corpus:
        image = corpus.image(observation_id)
    return Response(
        content=image.data,
        media_type=image.mime,
        headers={"Cache-Control": "private, max-age=600", "X-Content-Type-Options": "nosniff"},
    )
