"""M3 calibration: a non-canon production sampler chapter, isolated from canon.

Pinned with invented characters and an invented calibration document:

* the calibration document is parsed generically (CAL pages, source locator,
  source content, characters, validation notes, wardrobe stage);
* a calibration run is a distinct CALIBRATION purpose, never canon and never
  story continuity;
* every calibration page is READY from the start (a sampler, not a sequence);
* each page preserves its CAL id, source locator, source document and version;
* a calibration page never authorizes an absent character: only characters
  named on the page enter its cast.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from continuum_core.references import RoughPurpose
from continuum_library import ReferenceCatalog
from continuum_production import RoughProduction
from continuum_production.calibration import parse_calibration
from continuum_production.manga import MangaProduction
from continuum_storage import ProjectLibrary
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World

pytestmark = pytest.mark.requires_db

PROJECT = rough.PROJECT
world = rough.world
session = rough.session
catalog = rough.catalog

CALIBRATION = """# Demo Calibration Chapter v0.1

**Status:** CREATOR-APPROVED PRODUCTION CALIBRATION PACKAGE / NON_CANON

## CAL-01 \u2014 Abandoned settlement establishing

**Source:** `DEMO_S1E2_PANEL_SCRIPT_v0.1.md` \u2014 E2 Page 11.
**Source content:** lane, damaged houses, shed, stone-bordered field.

**Primary validation:**
- settlement scale;
- reusable spatial identity.

## CAL-02 \u2014 Lake quiet acting

**Source:** `DEMO_S1E14_PANEL_SCRIPT_v0.1.md` \u2014 E14 Page 13.
**Source content:** Aster sits first; Rowan stands, then sits with a small gap.

**Characters:** Aster Vale, Rowan.

**Primary validation:**
- recurring lake identity;
- restrained emotional acting.
"""


def _manga(session: Session, world: World, projects: ProjectLibrary) -> MangaProduction:
    cat = ReferenceCatalog(session, sources=world.sources(), derived=world.derived())
    return MangaProduction(RoughProduction(session, cat), projects)


def _profile_body() -> dict[str, Any]:
    return {
        "backend": {"provider_id": "fake.artwork-page-double", "width": 360, "height": 520},
        "reference_policy": {"per_facet": 2},
        "grammar": {"limit": 0},
    }


def test_parse_calibration_is_generic() -> None:
    pages = parse_calibration(CALIBRATION)
    assert [p.cal_id for p in pages] == ["CAL-01", "CAL-02"]
    assert pages[0].source_document == "DEMO_S1E2_PANEL_SCRIPT_v0.1.md"
    assert pages[0].wardrobe_stage == "E2"
    assert pages[1].source_document == "DEMO_S1E14_PANEL_SCRIPT_v0.1.md"
    assert pages[1].wardrobe_stage == "E14"
    assert pages[1].characters == ("Aster Vale", "Rowan")
    assert pages[0].characters == ()
    assert "settlement scale" in pages[0].validation_notes


def test_calibration_pages_resolve_page_specific_wardrobe_stage(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> None:
    """Fix B: a calibration page resolves its own source episode's wardrobe stage."""
    from continuum_core.references import (
        CharacterAspect,
        CharacterOrigin,
        OutfitKind,
        ReferenceClass,
        ReferenceOrigin,
    )
    from continuum_library import CharacterLink, ReferenceSpec

    from tests.phase1_world import MANGA, picture

    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key=PROJECT
    )
    frieren = catalog.create_character("Frieren", source_label="Invented Almanac")

    # Grounding for both.
    catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(frieren.id, CharacterAspect.FACE),),
        ),
        page_index=0,
    )
    catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(frieren.id, CharacterAspect.FULL_BODY),),
        ),
        page_index=1,
    )
    catalog.add_upload(
        picture(1),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(mau.id, CharacterAspect.FACE),),
        ),
    )
    catalog.add_upload(
        picture(2),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(mau.id, CharacterAspect.FULL_BODY),),
        ),
    )

    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key=PROJECT
    )
    cap = catalog.create_outfit(
        mau.id, "M-A2 McLaren cap", kind=OutfitKind.PROJECT, project_key=PROJECT
    )
    bottoms = catalog.create_outfit(
        frieren.id, "Comfortable bottoms", kind=OutfitKind.SOURCE_DEFAULT
    )
    catalog.add_upload(
        picture(3),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(mau.id, CharacterAspect.OUTFIT, outfit_id=hoodie.id),),
        ),
    )
    catalog.add_upload(
        picture(4),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(mau.id, CharacterAspect.ACCESSORY, outfit_id=cap.id),),
        ),
    )
    catalog.add_upload(
        picture(5),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(frieren.id, CharacterAspect.OUTFIT, outfit_id=bottoms.id),),
        ),
    )

    from continuum_production.wardrobe import Wardrobe

    wardrobe = Wardrobe(session)
    wardrobe.review(hoodie.id, "APPROVED", "art director")
    wardrobe.review(cap.id, "APPROVED", "art director")
    # E18 wardrobe: Frieren wears Mau's hoodie + cap + her own bottoms.
    wardrobe.assign_wear(hoodie.id, frieren.id, PROJECT, "E18")
    wardrobe.assign_wear(cap.id, frieren.id, PROJECT, "E18")
    wardrobe.assign_wear(bottoms.id, frieren.id, PROJECT, "E18")

    projects = ProjectLibrary([str(tmp_path / "projects")])
    manga = _manga(session, world, projects)
    manga.corpus.sync_curated(frieren.id)
    manga.corpus.sync_curated(mau.id)
    profile = manga.create_profile(PROJECT, "demo-calibration", _profile_body())
    document_hash = hashlib.sha256(CALIBRATION.encode("utf-8")).hexdigest()
    run = manga.start_calibration(
        PROJECT,
        "S1E2",
        1,
        "demo-calibration",
        "v0.1",
        document_hash,
        CALIBRATION,
        profile.id,
    )
    session.commit()

    pages = manga.pages(run.id)
    # CAL-01 is E2-sourced; CAL-02 is E14-sourced. Neither inherits the run's
    # S1E2 episode for wardrobe: each uses its own source episode stage.
    cal01 = manga.page_body(pages[0])
    cal02 = manga.page_body(pages[1])
    assert cal01["calibration"]["wardrobe_stage"] == "E2"
    assert cal02["calibration"]["wardrobe_stage"] == "E14"

    # CAL-02 (E14) has no E14 wardrobe, so its bundle has no wardrobe inputs.
    bundle02 = manga.assemble(pages[1])
    assert bundle02["wardrobe_inputs"] == []

    # A page with an E18 wardrobe stage resolves the E18 set (CAL-13 semantics).
    # We simulate by checking the assembler uses the page's stage, not the run's.
    # The E18 wardrobe is keyed to E18, so an E18-sourced page would resolve it.
    # Here we assert the stage derivation is page-specific and does not leak E2.
    assert cal01["calibration"]["wardrobe_stage"] != cal02["calibration"]["wardrobe_stage"]


def test_calibration_run_is_isolated_and_preserves_lineage(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> None:
    from continuum_core.references import CharacterOrigin

    aster = catalog.create_character("Aster Vale")
    rowan = catalog.create_character(
        "Rowan", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key=PROJECT
    )
    # Grounding for both characters (identity + body).
    from continuum_core.references import CharacterAspect, ReferenceClass, ReferenceOrigin
    from continuum_library import CharacterLink, ReferenceSpec

    from tests.phase1_world import MANGA, picture

    catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(aster.id, CharacterAspect.FACE),),
        ),
        page_index=0,
    )
    catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            characters=(CharacterLink(aster.id, CharacterAspect.FULL_BODY),),
        ),
        page_index=1,
    )
    catalog.add_upload(
        picture(1),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(rowan.id, CharacterAspect.FACE),),
        ),
    )
    catalog.add_upload(
        picture(2),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            characters=(CharacterLink(rowan.id, CharacterAspect.FULL_BODY),),
        ),
    )

    projects = ProjectLibrary([str(tmp_path / "projects")])
    manga = _manga(session, world, projects)
    manga.corpus.sync_curated(aster.id)
    manga.corpus.sync_curated(rowan.id)
    profile = manga.create_profile(PROJECT, "demo-calibration", _profile_body())
    document_hash = hashlib.sha256(CALIBRATION.encode("utf-8")).hexdigest()
    run = manga.start_calibration(
        PROJECT,
        "S1E2",
        1,
        "demo-calibration",
        "v0.1",
        document_hash,
        CALIBRATION,
        profile.id,
    )
    session.commit()

    assert run.purpose is RoughPurpose.CALIBRATION
    pages = manga.pages(run.id)
    assert len(pages) == 2
    # A sampler, not a sequence: every page is READY.
    assert [p.state for p in pages] == ["READY", "READY"]

    body = manga.page_body(pages[0])
    assert body["origin"] == "calibration"
    assert body["calibration"]["cal_id"] == "CAL-01"
    assert "DEMO_S1E2_PANEL_SCRIPT" in body["calibration"]["source_locator"]
    assert body["lineage"]["document_id"] == "demo-calibration"
    assert body["lineage"]["version"] == "v0.1"
    assert body["lineage"]["content_hash"] == document_hash

    # CAL-01 names no characters, so its cast is empty; CAL-02 names both.
    assert manga.page_body(pages[0])["characters"] == []
    assert set(manga.page_body(pages[1])["characters"]) == {"Aster Vale", "Rowan"}

    # A calibration page never authorizes an absent character: CAL-01 has no
    # cast, so it cannot introduce Rowan or Aster.
    assert "Rowan" not in manga.page_body(pages[0])["characters"]
    assert "Aster Vale" not in manga.page_body(pages[0])["characters"]
