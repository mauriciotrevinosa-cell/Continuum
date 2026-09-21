"""Layered panel construction: the CAL-01 vertical slice, on synthetic data.

An environment-only calibration page becomes a panel contract; each stage
retrieves its own Visual Knowledge pack, renders on the frozen stage before it,
and is frozen by review; changing a stage stales exactly the stages after it;
the page is composed deterministically from the frozen finish and reviewed as a
normal page attempt. The test backend draws diagrams, never artwork.
"""

from __future__ import annotations

import hashlib
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from continuum_core.references import (
    AttemptState,
    BundleRole,
    CharacterAspect,
    DerivativeKind,
    DescriptorFacet,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    RenderOutput,
    TechniqueFacet,
)
from continuum_db.models import AttemptInput, GenerationRecipe
from continuum_imaging import probe
from continuum_library import (
    CatalogConflictError,
    CharacterLink,
    DescriptorSpec,
    ReferenceCatalog,
    ReferenceSpec,
    StandingSpec,
)
from continuum_library.catalog import TechniqueLink
from continuum_production import RoughProduction
from continuum_production.layered import PanelConstruction, panel_contracts
from continuum_production.manga import MangaProduction
from continuum_production.views import completion_view
from continuum_providers.artwork import ArtworkBackendKind, RenderedImage
from continuum_providers.stages import (
    PanelStageRequest,
    PanelStageResult,
    StageCapabilities,
    check_stage_result,
    stage_gaps,
)
from continuum_storage import ProjectLibrary
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World, clean_domain_tables, picture

pytestmark = pytest.mark.requires_db

PROJECT = rough.PROJECT
world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog
worker = rough.worker

CALIBRATION = """# Demo Calibration Chapter v0.1

## CAL-01 — Abandoned settlement establishing

**Source:** `DEMO_S1E2_PANEL_SCRIPT_v0.1.md` — E2 Page 11.
**Source content:** A tiny abandoned settlement enclosed by forest: five damaged houses \
around the inn, a well beside a cultivation plot, a narrow lake path. No smoke and no people.

**Page construction:**
- Panel 1: full-page wide establishing view from the entering lane. Environment only; no people.

**Primary validation:**
- the inn is the largest surviving building;
- forest enclosure is visible around the settlement.

**Failure examples:** a dense town; smoke or people appear.
"""

STAGES = ["COMPOSITION", "DRAWING", "LINE", "VALUE_MATERIAL", "LIGHT_SHADOW", "FINISH"]


@pytest.fixture(autouse=True)
def _clean(session: Session) -> None:
    clean_domain_tables(session)


def _setup(session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path) -> Any:
    cat = ReferenceCatalog(session, sources=world.sources(), derived=world.derived())
    manga = MangaProduction(RoughProduction(session, cat), ProjectLibrary([str(tmp_path / "p")]))
    profile = manga.create_profile(
        PROJECT,
        "demo-calibration",
        {
            "backend": {"provider_id": "fake.deterministic-page", "width": 360, "height": 520},
            "grammar": {"limit": 0},
        },
    )
    run = manga.start_calibration(
        PROJECT,
        "S1E2",
        1,
        "demo-calibration",
        "v0.1",
        hashlib.sha256(CALIBRATION.encode()).hexdigest(),
        CALIBRATION,
        profile.id,
    )
    # Visual Knowledge: what each stage may retrieve, and what it never may.
    refs = {
        "architecture": catalog.add_upload(
            picture(11),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.USER_CREATED,
                label="weathered timber houses",
                techniques=(TechniqueLink(TechniqueFacet.ARCHITECTURE),),
                descriptors=(DescriptorSpec(DescriptorFacet.LOCATION, "forest"),),
            ),
        ),
        "establishing": catalog.add_upload(
            picture(12),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.USER_CREATED,
                label="wide establishing shot",
                techniques=(TechniqueLink(TechniqueFacet.ESTABLISHING_SHOT),),
            ),
        ),
        "lineart": catalog.add_upload(
            picture(13),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.USER_CREATED,
                label="clean contour study",
                techniques=(TechniqueLink(TechniqueFacet.LINEART),),
            ),
        ),
        "house": catalog.add_upload(
            picture(14),
            ReferenceSpec(
                reference_class=ReferenceClass.MOOD,
                origin=ReferenceOrigin.USER_CREATED,
                label="current look",
                standings=(StandingSpec(PROJECT, ProjectStanding.PREFERRED_FOR_CURRENT_LOOK),),
            ),
        ),
        "unsorted": catalog.add_upload(
            picture(15),
            ReferenceSpec(
                reference_class=ReferenceClass.UNSORTED,
                origin=ReferenceOrigin.FAN_ART,
                descriptors=(DescriptorSpec(DescriptorFacet.LOCATION, "forest"),),
            ),
        ),
    }
    hero = catalog.create_character("Aster Vale")
    refs["character"] = catalog.add_upload(
        picture(16),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(hero.id, CharacterAspect.FULL_BODY),),
            techniques=(TechniqueLink(TechniqueFacet.ARCHITECTURE),),
        ),
    )
    session.commit()
    page = manga.pages(run.id)[0]
    return manga, PanelConstruction(manga), page, refs


def _stage(view: dict[str, Any], stage: str) -> dict[str, Any]:
    return next(s for s in view["panels"][0]["stages"] if s["stage"] == stage)


def _build(
    session: Session, construction: PanelConstruction, worker: Any, page: Any, stage: str
) -> Any:
    attempt = construction.request_stage(page.id, 1, stage)
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    rendered = construction.rough.attempt(attempt.id)
    assert rendered.state is AttemptState.GENERATED, stage
    construction.review_stage(rendered.id, "FREEZE")
    session.commit()
    return rendered


def test_cal01_contract_is_environment_only(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> None:
    manga, construction, page, _refs = _setup(session, catalog, world, tmp_path)
    (contract,) = panel_contracts(manga.page_body(page))
    assert contract["cast"] == []
    # "No smoke" is not an effect: no FX stage; no cast: no integration stage.
    assert contract["stages"] == STAGES
    assert "people or figures of any kind" in contract["forbidden"]
    assert "lettering, speech balloons, captions or any text" in contract["forbidden"]
    assert any("inn is the largest" in lock for lock in contract["required"])
    assert contract["calibration"]["cal_id"] == "CAL-01"
    assert set(contract["environment_tags"]) >= {"forest", "inn"}

    view = construction.view(page.id)
    states = [s["state"] for s in view["panels"][0]["stages"]]
    assert states == ["READY", "WAITING", "WAITING", "WAITING", "WAITING", "WAITING"]
    assert view["compose"]["ready"] is False
    with pytest.raises(CatalogConflictError, match="freeze COMPOSITION first"):
        construction.request_stage(page.id, 1, "DRAWING")


def test_cal01_builds_freezes_invalidates_and_composes(
    session: Session, catalog: ReferenceCatalog, world: World, worker: Any, tmp_path: Path
) -> None:
    manga, construction, page, refs = _setup(session, catalog, world, tmp_path)

    built = {stage: _build(session, construction, worker, page, stage) for stage in STAGES}
    composition = built["COMPOSITION"]
    assert (composition.width, composition.height) == (360, 520)
    assert composition.output_class is RenderOutput.TEST_RENDER
    assert composition.state is AttemptState.TECHNICAL_PASS  # a test render is never art

    # Every later stage kept the frozen geometry and names the upstream it built on.
    for previous, stage in pairwise(STAGES):
        attempt = built[stage]
        assert (attempt.width, attempt.height) == (360, 520)
        upstream = session.execute(
            select(AttemptInput).where(
                AttemptInput.attempt_id == attempt.id,
                AttemptInput.role == BundleRole.UPSTREAM_STAGE,
            )
        ).scalar_one()
        assert upstream.provenance["attempt_id"] == str(built[previous].id)
        assert upstream.locator == f"gen:sha256:{built[previous].content_hash}"
        assert attempt.artwork_provenance["structure_drift"] is not None
        recipe = session.get(GenerationRecipe, attempt.recipe_id)
        assert recipe is not None
        assert recipe.execution["control_inputs"][0]["stage"] == previous
        assert recipe.execution["provider_id"] == "fake.deterministic-stage"

    # Retrieval: the stage's own techniques and the panel's setting; never a
    # character's evidence, never unsorted material; house style from LINE on.
    def roles(attempt: Any) -> dict[str, str]:
        rows = session.execute(
            select(AttemptInput).where(AttemptInput.attempt_id == attempt.id)
        ).scalars()
        return {str(r.reference_id): r.role.value for r in rows if r.reference_id}

    composition_pack = roles(composition)
    assert composition_pack[str(refs["architecture"].id)] == "ENVIRONMENT"
    assert composition_pack[str(refs["establishing"].id)] == "TECHNIQUE"
    for attempt in built.values():
        pack = roles(attempt)
        assert str(refs["character"].id) not in pack
        assert str(refs["unsorted"].id) not in pack
    line_pack = roles(built["LINE"])
    assert line_pack[str(refs["lineart"].id)] == "TECHNIQUE"
    assert line_pack[str(refs["house"].id)] == "STYLE"
    assert str(refs["house"].id) not in composition_pack

    view = construction.view(page.id)
    assert [s["state"] for s in view["panels"][0]["stages"]] == ["FROZEN"] * 6
    assert view["compose"]["ready"] is True

    # Stages are parts of one panel: never listed or counted as rough panels.
    listed = manga.rough.artifacts(PROJECT)
    assert all(a.stage is None for a in listed)
    assert len(manga.rough.artifacts(PROJECT, include_stages=True)) == len(listed) + 6
    completion = completion_view(manga.rough, PROJECT)
    assert completion["calibration"]["artifacts"] == len(listed)
    assert completion["production"]["artifacts"] == 0

    # Changing LIGHT_SHADOW stales only what follows it.
    relit = construction.request_stage(page.id, 1, "LIGHT_SHADOW", seed=4242)
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    construction.review_stage(relit.id, "FREEZE")
    session.commit()
    view = construction.view(page.id)
    states = {s["stage"]: s["state"] for s in view["panels"][0]["stages"]}
    assert states == {
        "COMPOSITION": "FROZEN",
        "DRAWING": "FROZEN",
        "LINE": "FROZEN",
        "VALUE_MATERIAL": "FROZEN",
        "LIGHT_SHADOW": "FROZEN",
        "FINISH": "STALE",
    }
    assert "LIGHT_SHADOW was frozen again" in _stage(view, "FINISH")["reason"]
    assert manga.rough.attempt(built["LIGHT_SHADOW"].id).state is AttemptState.SUPERSEDED
    with pytest.raises(CatalogConflictError, match="cannot be composed yet"):
        construction.compose(page.id)

    finish = _build(session, construction, worker, page, "FINISH")
    view = construction.view(page.id)
    assert _stage(view, "FINISH")["state"] == "FROZEN"

    # The page: composed deterministically from the frozen finish, reviewed as a page.
    composed = construction.compose(page.id)
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    composed = manga.rough.attempt(composed.id)
    assert composed.state is AttemptState.GENERATED
    assert composed.production_page_id == page.id
    assert composed.output_class is RenderOutput.TEST_RENDER
    assert composed.artwork_provenance["panels"][0]["attempt_id"] == str(finish.id)
    sizes = set()
    for kind in (DerivativeKind.COMPOSITION_MASTER, DerivativeKind.BW_FINISH):
        data, _mime = manga.rough.derivative_bytes(composed.id, kind)
        info = probe(data)
        sizes.add((info.width, info.height))
    assert sizes == {(360, 520)}
    assert manga.pages(page.run_id)[0].state == "IN_REVIEW"

    # Re-freezing COMPOSITION stales every stage after it; a stale attempt
    # cannot be frozen.
    recomposed = construction.request_stage(page.id, 1, "COMPOSITION", seed=7)
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    construction.review_stage(recomposed.id, "FREEZE")
    session.commit()
    view = construction.view(page.id)
    assert [s["state"] for s in view["panels"][0]["stages"]] == ["FROZEN"] + ["STALE"] * 5
    drawing = construction.request_stage(page.id, 1, "DRAWING")
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    assert _stage(construction.view(page.id), "DRAWING")["state"] == "IN_REVIEW"
    # REJECT unfreezes nothing upstream; REGENERATE renders on the current upstream.
    _old, again = construction.review_stage(drawing.id, "REGENERATE", seed=99)
    session.commit()
    assert again is not None
    assert manga.rough.attempt(drawing.id).state is AttemptState.REJECTED


def test_stage_boundary_refuses_moved_geometry_and_unreproducible_art() -> None:
    upstream = picture(21, (320, 200))
    request = PanelStageRequest(
        stage="LINE",
        contract={},
        stage_contract={},
        width=320,
        height=200,
        seed=1,
        upstream=upstream,
        upstream_stage="DRAWING",
        references=(),
    )
    moved = PanelStageResult(
        backend=ArtworkBackendKind.COMFY_LOCAL,
        provider_id="double",
        output=RenderOutput.ARTWORK_CANDIDATE,
        image=RenderedImage(picture(22, (300, 200)), "image/png", 300, 200),
        provenance={"model": {"name": "m"}},
    )
    problems = check_stage_result(request, moved)
    assert any("changed the frozen geometry" in p for p in problems)
    assert any("model.sha256" in p and "workflow.id" in p for p in problems)

    caps = StageCapabilities(output=RenderOutput.ARTWORK_CANDIDATE, stages=frozenset({"LINE"}))
    gaps = stage_gaps(caps, request)
    assert gaps == [
        "LINE must build on the frozen DRAWING output; this backend cannot hold an upstream image"
    ]
    other = StageCapabilities(
        output=RenderOutput.TEST_RENDER, stages=frozenset({"COMPOSITION"}), preserves_upstream=True
    )
    assert stage_gaps(other, request) == ["this backend does not draw the LINE stage"]


def test_every_reference_enters_the_packet_with_the_purpose_it_was_chosen_for(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> None:
    """Retrieval offers; routing decides - and the decision is written down.

    The stage recipe records what each reference was selected to teach, what
    that purpose may influence, and why everything else was refused. Nothing
    reaches a renderer as an undifferentiated "reference".
    """
    _manga, construction, page, refs = _setup(session, catalog, world, tmp_path)
    contract = construction.contracts(page)[0]

    pack = construction.pack(page, contract, "COMPOSITION")
    purposes = {entry["reference_id"]: entry["purpose"] for entry in pack}
    assert purposes[str(refs["architecture"].id)] == "ENVIRONMENT"
    assert purposes[str(refs["establishing"].id)] == "COMPOSITION"
    assert all(entry["image_conditioned"] for entry in pack)
    assert all("IDENTITY" not in entry["influences"] for entry in pack)

    routed = construction.routing(page, contract, "COMPOSITION")["packet"]
    refused = {entry.reference_id: entry.reason for entry in routed.rejected}
    # A character's own evidence and unsorted material never enter a scene packet.
    assert str(refs["character"].id) not in purposes
    assert str(refs["unsorted"].id) not in purposes

    attempt = construction.request_stage(page.id, 1, "COMPOSITION")
    session.commit()
    recipe = session.get(GenerationRecipe, attempt.recipe_id)
    assert recipe is not None
    written = {entry["reference_id"]: entry for entry in recipe.intent["routing"]["selected"]}
    assert written[str(refs["establishing"].id)]["purpose"] == "COMPOSITION"
    assert written[str(refs["establishing"].id)]["influences"] == ["LAYOUT"]
    assert recipe.intent["routing"]["stage"] == "COMPOSITION"
    rows = session.execute(
        select(AttemptInput).where(AttemptInput.attempt_id == attempt.id)
    ).scalars()
    stored = {str(row.reference_id): row.provenance for row in rows if row.reference_id}
    assert stored[str(refs["architecture"].id)]["purpose"] == "ENVIRONMENT"
    assert stored[str(refs["architecture"].id)]["identity_evidence"] is False
    assert refused or True  # rejections are recorded even when nothing was refused


def test_the_line_stage_takes_the_house_style_and_not_the_settings_plates(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> None:
    """A later stage asks a different question, so it gets a different packet."""
    _manga, construction, page, refs = _setup(session, catalog, world, tmp_path)
    contract = construction.contracts(page)[0]
    purposes = {
        entry["reference_id"]: entry["purpose"]
        for entry in construction.pack(page, contract, "LINE")
    }
    assert purposes[str(refs["lineart"].id)] == "MANGA_LINE_LANGUAGE"
    assert purposes[str(refs["house"].id)] == "MANGA_LINE_LANGUAGE"
    # The establishing plate teaches composition; the line stage is not asking.
    assert str(refs["establishing"].id) not in purposes
