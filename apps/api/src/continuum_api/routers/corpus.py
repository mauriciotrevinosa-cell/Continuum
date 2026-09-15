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
    ObservationAuthority,
    ObservationFacet,
    ObservationRole,
    ObservationSource,
    ObservationStatus,
    ViewAngle,
)
from continuum_imaging.manga import analyze_layout
from continuum_production.corpus import CharacterCorpus, observation_view
from continuum_production.manga import source_page_reader
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


class EnvironmentIn(StrictBody):
    tags: list[str] = Field(min_length=1, max_length=8)


@router.get("/library/characters/{character_id}/overview")
def character_overview(request: Request, character_id: uuid.UUID) -> dict[str, Any]:
    """Who the character is, what they should look like, how well grounded, and on what."""
    with corpus_scope(request) as corpus:
        corpus.sync_curated(character_id)
        return corpus.overview(character_id)


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
