"""Page-by-page manga production routes (M3): profiles, runs, pages, review.

The API records and **enqueues**; the worker renders (ADR-0002). Records are
addressed by id (F-50); chapter text is read from the project's committed
sources, never taken from the client. Page images are served by the existing
attempt image route (``kind=COMPOSITION_MASTER | BW_FINISH | COLOR_FINISH``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

from continuum_core.references import ReviewDecision, RoughPurpose
from continuum_db.models import PageDependency, ProductionPage, ProductionProfile, ProductionRun
from continuum_imaging.manga import analyze_layout
from continuum_production import RoughProduction, attempt_view
from continuum_production.manga import (
    GrammarCandidate,
    MangaProduction,
    catalog_grammar_candidates,
    source_page_reader,
)
from continuum_production.materialize import PlacementDecision
from continuum_production.views import attempt_summary
from continuum_providers import ProviderRegistry
from continuum_storage import ProjectLibrary
from fastapi import APIRouter, Request
from fastapi import Path as PathParam
from pydantic import Field
from sqlalchemy import select

from continuum_api.routers.library import StrictBody, catalog_scope

router = APIRouter(tags=["manga-production"])

ProjectId = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]
Episode = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")]
FINISHES = ("COMPOSITION_MASTER", "BW_FINISH", "COLOR_FINISH")


@contextmanager
def manga_scope(request: Request) -> Iterator[MangaProduction]:
    state = request.app.state
    providers: ProviderRegistry = state.providers
    projects: ProjectLibrary = state.projects
    cache: dict[str, GrammarCandidate] = state.__dict__.setdefault("grammar_layouts", {})
    with catalog_scope(request) as catalog:
        rough = RoughProduction(catalog.session, catalog, providers=providers)
        grammar = catalog_grammar_candidates(
            catalog.session, source_page_reader(catalog), analyze_layout, cache
        )
        yield MangaProduction(rough, projects, grammar_candidates=grammar)


# ---------------------------------------------------------------------------
class DecisionIn(StrictBody):
    item_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    chapter: int = Field(ge=1, le=1000)
    after_base_page: int = Field(ge=0, le=100_000)
    #: PROPOSED placements are enough for a sample; canonical production needs CONFIRMED.
    status: str = Field(default="PROPOSED", pattern=r"^(PROPOSED|CONFIRMED)$")
    author: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=2000)

    def decision(self) -> PlacementDecision:
        return PlacementDecision(**self.model_dump())


class ProfileIn(StrictBody):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    body: dict[str, Any]


class MaterializeIn(StrictBody):
    chapter: int = Field(ge=1, le=1000)
    decisions: list[DecisionIn] = Field(default_factory=list, max_length=50)


class RunIn(StrictBody):
    episode: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
    purpose: RoughPurpose
    profile_id: uuid.UUID
    chapters: list[int] = Field(min_length=1, max_length=20)
    decisions: list[DecisionIn] = Field(default_factory=list, max_length=50)


class ReadinessIn(StrictBody):
    profile_id: uuid.UUID
    chapters: list[int] = Field(min_length=1, max_length=20)
    decisions: list[DecisionIn] = Field(default_factory=list, max_length=50)


class PageAttemptIn(StrictBody):
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    notes: str = Field(default="", max_length=8000)


class PageReviewIn(StrictBody):
    decision: ReviewDecision
    notes: str = Field(default="", max_length=8000)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class SampleDecisionIn(StrictBody):
    passed: bool
    notes: str = Field(default="", max_length=8000)


# ---------------------------------------------------------------------------
def _profile_view(profile: ProductionProfile) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "name": profile.name,
        "version": profile.version,
        "status": profile.status,
        "body": profile.body,
        "hash": profile.body_hash,
        "promoted_from_run": str(profile.promoted_from_run) if profile.promoted_from_run else None,
    }


def _images(attempt_id: uuid.UUID | None) -> dict[str, str] | None:
    if attempt_id is None:
        return None
    return {kind: f"/production/attempts/{attempt_id}/image?kind={kind}" for kind in FINISHES}


def _page_summary(manga: MangaProduction, page: ProductionPage) -> dict[str, Any]:
    attempts = manga.rough.attempts(page.artifact_id)
    latest = attempts[0] if attempts else None  # newest first
    shown = page.approved_attempt_id or (latest.id if latest else None)
    body = manga.page_body(page)
    return {
        "id": str(page.id),
        "sequence": page.sequence,
        "page_key": page.page_key,
        "integrated_page": body["integrated_page"],
        "label": body["label"],
        "state": page.state,
        "reasons": page.reasons,
        "approved_attempt_id": str(page.approved_attempt_id) if page.approved_attempt_id else None,
        "latest_attempt_id": str(latest.id) if latest else None,
        "attempt_count": len(attempts),
        "images": _images(shown),
    }


def _run_view(manga: MangaProduction, run: ProductionRun) -> dict[str, Any]:
    profile = manga.session.get(ProductionProfile, run.profile_id)
    assert profile is not None
    continuity = manga.current_continuity(run.id)
    upcoming = manga.next_page(run.id)
    return {
        "id": str(run.id),
        "project_key": run.project_key,
        "episode": run.episode,
        "chapter": run.chapter,
        "purpose": run.purpose.value,
        "status": run.status,
        "decision_notes": run.decision_notes,
        "profile": _profile_view(profile),
        "continuity": {
            "id": str(continuity.id),
            "version": continuity.version,
            "reason": continuity.reason,
            "body": continuity.body,
        },
        "next_page_id": str(upcoming.id) if upcoming else None,
        "pages": [_page_summary(manga, page) for page in manga.pages(run.id)],
    }


def _run(manga: MangaProduction, run_id: uuid.UUID) -> ProductionRun:
    from continuum_library import CatalogNotFoundError

    run = manga.session.get(ProductionRun, run_id)
    if run is None:
        raise CatalogNotFoundError("That production run does not exist.")
    return run


def _page(manga: MangaProduction, page_id: uuid.UUID) -> ProductionPage:
    from continuum_library import CatalogNotFoundError

    page = manga.session.get(ProductionPage, page_id)
    if page is None:
        raise CatalogNotFoundError("That production page does not exist.")
    return page


# ---------------------------------------------------------------------------
@router.get("/projects/{project_id}/production-profiles")
def list_profiles(request: Request, project_id: ProjectId) -> list[dict[str, Any]]:
    with manga_scope(request) as manga:
        rows = manga.session.execute(
            select(ProductionProfile)
            .where(ProductionProfile.project_key == project_id)
            .order_by(ProductionProfile.name, ProductionProfile.version)
        ).scalars()
        return [_profile_view(row) for row in rows]


@router.post("/projects/{project_id}/production-profiles", status_code=201)
def create_profile(request: Request, project_id: ProjectId, body: ProfileIn) -> dict[str, Any]:
    with manga_scope(request) as manga:
        return _profile_view(manga.create_profile(project_id, body.name, body.body))


@router.post("/projects/{project_id}/episodes/{episode}/materialize")
def materialize(
    request: Request, project_id: ProjectId, episode: Episode, body: MaterializeIn
) -> dict[str, Any]:
    with manga_scope(request) as manga:
        chapter = manga.materialize(
            project_id, episode, body.chapter, [d.decision() for d in body.decisions]
        )
        return {"id": str(chapter.id), "hash": chapter.body_hash, "body": chapter.body}


@router.post("/projects/{project_id}/episodes/{episode}/canonical-readiness")
def canonical_readiness(
    request: Request, project_id: ProjectId, episode: Episode, body: ReadinessIn
) -> dict[str, Any]:
    """Why START CANONICAL PRODUCTION is not available yet - or that it is."""
    with manga_scope(request) as manga:
        reasons = manga.canonical_start_readiness(
            project_id,
            episode,
            body.profile_id,
            body.chapters,
            [d.decision() for d in body.decisions],
        )
        return {"ready": not reasons, "reasons": reasons}


@router.get("/projects/{project_id}/production-runs")
def list_runs(request: Request, project_id: ProjectId) -> list[dict[str, Any]]:
    with manga_scope(request) as manga:
        rows = manga.session.execute(
            select(ProductionRun)
            .where(ProductionRun.project_key == project_id)
            .order_by(ProductionRun.created_at.desc())
        ).scalars()
        return [
            {
                "id": str(run.id),
                "episode": run.episode,
                "chapter": run.chapter,
                "purpose": run.purpose.value,
                "status": run.status,
            }
            for run in rows
        ]


@router.post("/projects/{project_id}/production-runs", status_code=201)
def start_run(request: Request, project_id: ProjectId, body: RunIn) -> dict[str, Any]:
    with manga_scope(request) as manga:
        run = manga.start_run(
            project_id,
            body.episode,
            purpose=body.purpose,
            profile_id=body.profile_id,
            chapters=body.chapters,
            decisions=[d.decision() for d in body.decisions],
        )
        return _run_view(manga, run)


@router.get("/production/runs/{run_id}")
def get_run(request: Request, run_id: uuid.UUID) -> dict[str, Any]:
    """The run with a lightweight contact sheet of every page."""
    with manga_scope(request) as manga:
        return _run_view(manga, _run(manga, run_id))


@router.post("/production/runs/{run_id}/refresh")
def refresh_run(request: Request, run_id: uuid.UUID) -> dict[str, Any]:
    """Re-check every page against current sources, references and profile."""
    with manga_scope(request) as manga:
        changes = manga.refresh_staleness(_run(manga, run_id).id)
        return {"changes": changes, "run": _run_view(manga, _run(manga, run_id))}


@router.post("/production/runs/{run_id}/sample-decision")
def sample_decision(request: Request, run_id: uuid.UUID, body: SampleDecisionIn) -> dict[str, Any]:
    """SAMPLE PASS promotes the profile (never the images); FAIL closes the sample."""
    with manga_scope(request) as manga:
        promoted = manga.decide_sample(run_id, passed=body.passed, notes=body.notes)
        return {
            "run": _run_view(manga, _run(manga, run_id)),
            "promoted_profile": _profile_view(promoted) if promoted else None,
        }


@router.get("/production/pages/{page_id}")
def get_page(request: Request, page_id: uuid.UUID) -> dict[str, Any]:
    """The current page: its script, what it will be drawn from, and every attempt."""
    with manga_scope(request) as manga:
        page = _page(manga, page_id)
        dependencies = manga.session.execute(
            select(PageDependency)
            .where(PageDependency.page_id == page.id)
            .order_by(PageDependency.kind, PageDependency.key)
        ).scalars()
        attempts = []
        for attempt in manga.rough.attempts(page.artifact_id):
            attempts.append(
                {
                    **attempt_summary(manga.rough, attempt),
                    "artwork_provenance": attempt.artwork_provenance,
                    "continuity_state_id": (
                        str(attempt.continuity_state_id) if attempt.continuity_state_id else None
                    ),
                    "images": _images(attempt.id),
                }
            )
        return {
            **_page_summary(manga, page),
            "run_id": str(page.run_id),
            "body": manga.page_body(page),
            "bundle": manga.assemble(page),
            "dependencies": [
                {"kind": d.kind, "key": d.key, "version_hash": d.version_hash} for d in dependencies
            ],
            "attempts": attempts,
        }


@router.post("/production/pages/{page_id}/attempts", status_code=202)
def request_page_attempt(
    request: Request, page_id: uuid.UUID, body: PageAttemptIn
) -> dict[str, Any]:
    with manga_scope(request) as manga:
        attempt = manga.request_page_attempt(page_id, seed=body.seed, notes=body.notes)
        return attempt_view(manga.rough, attempt)


@router.post("/production/page-attempts/{attempt_id}/review")
def review_page_attempt(
    request: Request, attempt_id: uuid.UUID, body: PageReviewIn
) -> dict[str, Any]:
    with manga_scope(request) as manga:
        new = manga.review_page(attempt_id, body.decision, notes=body.notes, seed=body.seed)
        page = _page(manga, manga.rough.attempt(attempt_id).production_page_id)  # type: ignore[arg-type]
        return {
            "page": _page_summary(manga, page),
            "regenerated": attempt_view(manga.rough, new) if new is not None else None,
        }
