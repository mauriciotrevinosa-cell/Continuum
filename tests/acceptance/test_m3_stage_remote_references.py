"""A layered stage on a remote GPU, end to end through the durable job (fake ComfyUI).

W01/CAL-01 found that one source manga page in a stage pack made the remote
backend refuse the whole stage, and that the approved environment reference
never conditioned the image. Here, through the real job path:

* retrieval selects both the project's environment reference and a source page;
* the source page is withheld (bytes never read, never uploaded) with a reason;
* the environment reference is sent and image-conditions COMPOSITION;
* lineage keeps selected / given / withheld apart;
* a cast member whose only identity evidence is a source excerpt stops the
  stage with an actionable reason instead of drawing a generic character.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from continuum_core.references import (
    AttemptState,
    CharacterAspect,
    DescriptorFacet,
    ReferenceClass,
    ReferenceOrigin,
    RenderOutput,
    TechniqueFacet,
)
from continuum_db.models import Job
from continuum_library import (
    CharacterLink,
    DescriptorSpec,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_library.catalog import TechniqueLink
from continuum_production import RoughProduction
from continuum_production.layered import PanelConstruction
from continuum_production.manga import MangaProduction
from continuum_providers import build_default_registry
from continuum_providers.artwork import ArtworkBackendKind
from continuum_storage import ProjectLibrary
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.acceptance.test_m3_comfy_backend import FakeComfy, _provider
from tests.phase1_world import MANGA, World, clean_domain_tables, picture

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
**Source content:** A tiny abandoned settlement enclosed by forest around the inn. No people.

**Page construction:**
- Panel 1: full-page wide establishing view from the entering lane. Environment only; no people.

**Primary validation:**
- the inn is the largest surviving building.

## CAL-02 — Lake quiet acting

**Source:** `DEMO_S1E14_PANEL_SCRIPT_v0.1.md` — E14 Page 13.
**Source content:** Aster Vale sits by the forest lake.

**Characters:** Aster Vale.

**Primary validation:**
- Aster Vale is recognisable.
"""


@pytest.fixture(autouse=True)
def _clean(session: Session) -> None:
    clean_domain_tables(session)


@pytest.fixture
def comfy() -> Iterator[FakeComfy]:
    with FakeComfy() as server:
        yield server


def _setup(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> tuple[MangaProduction, PanelConstruction, Any, dict[str, Any]]:
    cat = ReferenceCatalog(session, sources=world.sources(), derived=world.derived())
    manga = MangaProduction(RoughProduction(session, cat), ProjectLibrary([str(tmp_path / "p")]))
    hero = catalog.create_character("Aster Vale")
    # Aster Vale's only identity evidence is a page of the source manga.
    catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(hero.id, CharacterAspect.FACE),),
        ),
        page_index=0,
    )
    catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(hero.id, CharacterAspect.FULL_BODY),),
        ),
        page_index=1,
    )
    manga.corpus.sync_curated(hero.id)
    refs = {
        # The creator-approved environment image: the project's own.
        "inn": catalog.add_upload(
            picture(31),
            ReferenceSpec(
                reference_class=ReferenceClass.CANON,
                origin=ReferenceOrigin.USER_CREATED,
                label="approved inn exterior",
                techniques=(TechniqueLink(TechniqueFacet.ESTABLISHING_SHOT),),
                descriptors=(DescriptorSpec(DescriptorFacet.LOCATION, "forest"),),
            ),
        ),
        # A source manga page retrieved for the same setting.
        "source": catalog.add_from_source(
            world.id_of(MANGA),
            ReferenceSpec(
                reference_class=ReferenceClass.TECHNIQUE,
                origin=ReferenceOrigin.SOURCE,
                techniques=(TechniqueLink(TechniqueFacet.COMPOSITION),),
                descriptors=(DescriptorSpec(DescriptorFacet.LOCATION, "forest"),),
            ),
            page_index=2,
        ),
    }
    profile = manga.create_profile(
        PROJECT,
        "remote-stages",
        {
            "backend": {
                "provider_id": "fake.deterministic-page",
                "stage_provider_id": "comfy.remote",
                "width": 300,
                "height": 420,
            },
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
    session.commit()
    return manga, PanelConstruction(manga), manga.pages(run.id), refs


def _remote_worker(worker: Any, comfy: FakeComfy) -> None:
    registry = build_default_registry()
    registry.register(_provider(comfy.url, backend=ArtworkBackendKind.COMFY_REMOTE))
    worker.providers = registry


def test_remote_stage_withholds_source_pages_and_conditions_on_the_approved_environment(
    session: Session,
    catalog: ReferenceCatalog,
    world: World,
    worker: Any,
    comfy: FakeComfy,
    tmp_path: Path,
) -> None:
    manga, construction, pages, refs = _setup(session, catalog, world, tmp_path)
    _remote_worker(worker, comfy)
    attempt = construction.request_stage(pages[0].id, 1, "COMPOSITION")
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()
    rendered = manga.rough.attempt(attempt.id)
    job = session.get(Job, rendered.job_id)
    assert job is not None and job.status.value == "SUCCEEDED", job.last_error if job else None
    assert rendered.state is AttemptState.GENERATED
    assert rendered.output_class is RenderOutput.ARTWORK_CANDIDATE

    prov = rendered.artwork_provenance
    inn, source = str(refs["inn"].id), str(refs["source"].id)
    # Retrieval selected both; the source page is withheld with its reason.
    assert {e["reference_id"] for e in prov["references_selected"]} == {inn, source}
    assert prov["references_given"] == [inn]
    (withheld,) = prov["references_withheld"]
    assert withheld["reference_id"] == source
    assert "never leaves this machine" in withheld["reason"]
    # The approved environment really conditions the composition.
    assert prov["references_transmitted"] == [inn]
    assert prov["conditioning"]["scene"]["purpose"] == "COMPOSITION"
    assert prov["conditioning"]["scene"]["references"] == [inn]
    assert prov["conditioning"]["identity"] == {}
    # Exactly one image left the machine: the inn. The source page never did.
    assert len(comfy.uploads) == 1
    graph = comfy.prompts[-1]
    assert any(
        n["class_type"] == "IPAdapterAdvanced" and n["inputs"]["weight_type"] == "composition"
        for n in graph.values()
    )


def test_a_cast_whose_identity_is_only_source_excerpts_stops_with_a_reason(
    session: Session,
    catalog: ReferenceCatalog,
    world: World,
    worker: Any,
    comfy: FakeComfy,
    tmp_path: Path,
) -> None:
    manga, construction, pages, _refs = _setup(session, catalog, world, tmp_path)
    _remote_worker(worker, comfy)
    contract = construction.contracts(pages[1])[0]
    assert contract["cast"] == ["Aster Vale"]
    attempt = construction.request_stage(pages[1].id, 1, "COMPOSITION")
    session.commit()
    rough.drain(worker)
    session.expire_all()
    rendered = manga.rough.attempt(attempt.id)
    assert rendered.state is AttemptState.QUEUED  # nothing was drawn
    job = session.get(Job, rendered.job_id)
    assert job is not None and job.status.value == "BLOCKED"
    assert job.blocked_reason is not None
    message = str(job.remediation)
    assert "identity evidence of Aster Vale" in message
    assert "Source excerpts are never sent to a remote GPU" in message
    assert comfy.prompts == [] and comfy.uploads == []
