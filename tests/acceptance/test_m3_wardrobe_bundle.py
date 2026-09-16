"""M3 W8: the production bundle carries the story-stage wardrobe set, isolated from identity.

Pinned with invented characters:

* a page's bundle resolves the APPROVED wardrobe set for its episode stage;
* a wearer may combine borrowed APPROVED PROJECT garments with their own
  SOURCE/default garments in one set;
* owner and wearer stay separate per garment, and borrowing is flagged;
* wardrobe inputs are a distinct role (WARDROBE), never identity (CANON);
* wardrobe provenance records owner/wearer/borrowed/condition and marks
  ``identity_evidence: False``.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from continuum_core.references import (
    CharacterAspect,
    CharacterOrigin,
    OutfitKind,
    ReferenceClass,
    ReferenceOrigin,
    RoughPurpose,
)
from continuum_library import CharacterLink, ReferenceCatalog, ReferenceSpec
from continuum_production import RoughProduction
from continuum_production.manga import MangaProduction, _wardrobe_stage
from continuum_production.wardrobe import Wardrobe
from continuum_storage import ProjectLibrary
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import MANGA, World, picture

pytestmark = pytest.mark.requires_db

PROJECT = rough.PROJECT
world = rough.world
session = rough.session
catalog = rough.catalog

SCRIPT = """# HARBOR - S1E18 Manga Panel Script v0.1

**Status:** APPROVED PANEL SCRIPT

## Approved chapter cuts for rough

- **Chapter 1 \u2014 approx. pages 1\u20131:** the callback.

# SCENE 1 \u2014 CALLBACK

### Page 1
- Frieren sits by the lake.
"""


def _write_project(root: Path) -> ProjectLibrary:
    folder = root / "projects" / PROJECT
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "HARBOR_S1E18_MANGA_PANEL_SCRIPT_v0.1.md").write_text(SCRIPT, encoding="utf-8")
    (folder / "HARBOR_S1E18_DRAFT_1_v0.1.md").write_text(
        "# Harbor S1E18 Draft 1\n\n**Status:** APPROVED\n", encoding="utf-8"
    )
    entry = lambda path, doc_id, category, lifecycle="APPROVED", **extra: {  # noqa: E731
        "id": doc_id,
        "path": path,
        "category": category,
        "section": "production",
        "lifecycle": lifecycle,
        **extra,
    }
    manifest = {
        "id": PROJECT,
        "title": "Demo Project",
        "documents": [
            entry(
                "HARBOR_S1E18_MANGA_PANEL_SCRIPT_v0.1.md",
                "s1e18-panel",
                "panel-script",
                episode="S1E18",
            ),
            entry("HARBOR_S1E18_DRAFT_1_v0.1.md", "s1e18-draft", "draft", episode="S1E18"),
        ],
        "episodes": {
            "match": r"^S(?P<season>\d+)E(?P<number>\d+)$",
            "levels": [{"id": "4", "label": "Ready", "requires": ["draft", "panel-script"]}],
            "production_sources": [
                {"role": "base-panel-script", "categories": ["panel-script"], "required": True},
                {"role": "draft", "categories": ["draft"], "required": True},
            ],
        },
    }
    (folder / "continuum.project.json").write_text(json.dumps(manifest), encoding="utf-8")
    return ProjectLibrary([str(root / "projects")])


def _manga(session: Session, world: World, projects: ProjectLibrary) -> MangaProduction:
    cat = ReferenceCatalog(session, sources=world.sources(), derived=world.derived())
    return MangaProduction(RoughProduction(session, cat), projects)


def _profile_body() -> dict[str, Any]:
    return {
        "backend": {"provider_id": "fake.artwork-page-double", "width": 360, "height": 520},
        "reference_policy": {"per_facet": 2},
        "grammar": {"limit": 0},
    }


def test_wardrobe_stage_maps_episode_to_stage() -> None:
    assert _wardrobe_stage("S1E18") == "E18"
    assert _wardrobe_stage("S1E1") == "E1"
    assert _wardrobe_stage("E18") == "E18"


def test_production_bundle_carries_wardrobe_set_isolated_from_identity(
    session: Session, catalog: ReferenceCatalog, world: World, tmp_path: Path
) -> None:
    projects = _write_project(tmp_path)
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key=PROJECT
    )
    frieren = catalog.create_character("Frieren", source_label="Invented Almanac")

    # Grounding: Frieren from source, Mau from creator photos.
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

    # Appearance references linked to each garment (wardrobe, never identity).
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

    wardrobe = Wardrobe(session)
    wardrobe.review(hoodie.id, "APPROVED", "art director")
    wardrobe.review(cap.id, "APPROVED", "art director")
    wardrobe.assign_wear(hoodie.id, frieren.id, PROJECT, "E18")
    wardrobe.assign_wear(cap.id, frieren.id, PROJECT, "E18")
    wardrobe.assign_wear(bottoms.id, frieren.id, PROJECT, "E18")

    manga = _manga(session, world, projects)
    manga.corpus.sync_curated(frieren.id)
    manga.corpus.sync_curated(mau.id)
    profile = manga.create_profile(PROJECT, "harbor-manga", _profile_body())
    run = manga.start_run(
        PROJECT,
        "S1E18",
        purpose=RoughPurpose.NON_CANON_SAMPLE,
        profile_id=profile.id,
        chapters=[1],
    )
    session.commit()

    page = manga.pages(run.id)[0]
    assert page.state == "READY"
    bundle = manga.assemble(page)

    wardrobe_inputs = bundle["wardrobe_inputs"]
    names = {w["name"] for w in wardrobe_inputs}
    assert names == {"M-H1 McLaren hoodie", "M-A2 McLaren cap", "Comfortable bottoms"}

    by_name = {w["name"]: w for w in wardrobe_inputs}
    assert by_name["M-H1 McLaren hoodie"]["owner_character_id"] == str(mau.id)
    assert by_name["M-H1 McLaren hoodie"]["wearer_character_id"] == str(frieren.id)
    assert by_name["M-H1 McLaren hoodie"]["borrowed"] is True
    assert by_name["M-A2 McLaren cap"]["owner_character_id"] == str(mau.id)
    assert by_name["M-A2 McLaren cap"]["borrowed"] is True
    assert by_name["Comfortable bottoms"]["owner_character_id"] == str(frieren.id)
    assert by_name["Comfortable bottoms"]["borrowed"] is False

    # Wardrobe is a distinct role, never identity: it is not in canon_inputs.
    canon_outfit_ids = {c.get("outfit_id") for c in bundle["canon_inputs"] if c.get("outfit_id")}
    wardrobe_outfit_ids = {w["outfit_id"] for w in wardrobe_inputs}
    assert wardrobe_outfit_ids.isdisjoint(canon_outfit_ids)
    assert all(w["role"] == "WARDROBE" for w in wardrobe_inputs)
    assert all(w["why"] == ["story-stage approved wardrobe set"] for w in wardrobe_inputs)
