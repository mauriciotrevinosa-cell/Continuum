"""M3: the character reference corpus - a character is not one picture.

Pinned with invented characters and a synthetic catalog:

* curated references become confirmed observations whose authority follows
  their origin; a preferred franchise reference is a production anchor;
* the catalogued source manga is swept for candidate pages from the chapter
  of the character's first curated appearance; fan art whose labels name the
  character is a supplemental candidate; nothing is duplicated on refresh and
  a person's review is never overwritten;
* candidates never count toward readiness; readiness needs several confirmed,
  high-authority observations from independent sources; an atypical
  observation stays evidence and cannot redefine the character;
* retrieval follows the page's need (facet, angle, co-occurring characters),
  ranks by authority and status and prefers diverse sources;
* an original character is grounded only by the creator's own references; a
  stylized concept is stylization, never an anchor, never identity;
* a page can be taken as an environment reference with setting tags.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

from typing import Any

import pytest
from continuum_core.catalog import Confidence, DetectedKind, EntryStatus, MaterialClass, UnitKind
from continuum_core.references import (
    CharacterAspect,
    CharacterOrigin,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
)
from continuum_db.models import CatalogEntry, CatalogUnit
from continuum_imaging.manga import analyze_layout
from continuum_library import (
    CatalogInputError,
    CatalogNotFoundError,
    CharacterLink,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_production import RoughProduction
from continuum_production.corpus import CharacterCorpus, page_needs, setting_tags
from continuum_production.manga import MangaProduction, source_page_reader
from continuum_storage import ProjectLibrary
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import MANGA, World, picture

pytestmark = pytest.mark.requires_db

world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog


def _catalog_rows(session: Session) -> None:
    entry = CatalogEntry(
        root_key="source_vault",
        relative_path=MANGA,
        file_name="demo-orbit-v01.cbz",
        extension=".cbz",
        byte_size=1,
        mtime_ns=1,
        detected_kind=DetectedKind.ARCHIVE,
        status=EntryStatus.CATALOGUED,
        material_class=MaterialClass.MANGA,
        scanner_version=1,
        series_key="demo-orbit",
        series_title="Demo Orbit",
    )
    session.add(entry)
    session.flush()
    for number, first in ((1, 0), (2, 3), (3, 6)):
        session.add(
            CatalogUnit(
                unit_key=f"demo-orbit-ch{number}",
                entry_id=entry.id,
                kind=UnitKind.MANGA_CHAPTER,
                material_class=MaterialClass.MANGA,
                series_key="demo-orbit",
                series_title="Demo Orbit",
                label=f"Chapter {number}",
                sort_key=f"{number:04d}",
                first_page_index=first,
                page_count=3,
                confidence=Confidence.HIGH,
            )
        )
    session.flush()


def _corpus(catalog: ReferenceCatalog) -> CharacterCorpus:
    return CharacterCorpus(
        catalog.session, catalog, page_reader=source_page_reader(catalog), analyze=analyze_layout
    )


def _by_source(corpus: CharacterCorpus, character_id: Any) -> dict[str, Any]:
    return {row.source_label: row for row in corpus.observations(character_id)}


def test_franchise_character_corpus(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    aster = catalog.create_character("Aster Vale", source_label="Demo Orbit")
    beryl = catalog.create_character("Beryl", source_label="Demo Orbit")
    face = catalog.add_from_source(
        world.id_of(MANGA),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.SOURCE,
            label="Aster face",
            characters=(CharacterLink(aster.id, CharacterAspect.FACE, preferred=True),),
        ),
        page_index=0,
    )
    catalog.add_upload(
        picture(5),
        ReferenceSpec(
            reference_class=ReferenceClass.UNSORTED,
            origin=ReferenceOrigin.FAN_ART,
            label="someone_aster_vale_sketch_01",
        ),
    )
    _catalog_rows(session)
    session.commit()
    corpus = _corpus(catalog)

    summary = corpus.refresh(aster.id, analyze_limit=2)
    session.commit()
    assert summary["series"] == ["demo-orbit"]
    assert summary["source_pages_added"] == 6 and summary["fan_art_added"] == 1
    assert summary["layout_hints"] == 2, "only readable pages get hints"
    rows = _by_source(corpus, aster.id)
    anchor = rows["Aster face"]
    assert (anchor.status, anchor.authority, anchor.role, anchor.anchor) == (
        "CONFIRMED",
        "PRIMARY_SOURCE",
        "GROUNDING",
        True,
    )
    assert anchor.facets == ["FACE"]
    candidate = rows["Chapter 2 p2"]
    assert (candidate.status, candidate.authority, candidate.facets) == (
        "CANDIDATE",
        "PRIMARY_SOURCE",
        [],
    )
    fan = next(r for r in rows.values() if r.source_kind == "FAN_ART")
    assert (fan.status, fan.authority, fan.role) == ("CANDIDATE", "SUPPLEMENTAL", "EVIDENCE")
    assert rows["Chapter 1 p2"].evidence["framing_hint"] in {None, "WIDE", "CLOSE_UP"}

    # Candidates never count: one confirmed face, no body.
    ready = corpus.readiness(aster.id)
    assert (
        ready["groups"]["face"]["state"] == "PARTIAL"
        and ready["groups"]["body"]["state"] == "MISSING"
    )
    assert ready["grounded"] is False and ready["ungrounded"] == ["body"]

    need = {"facets": ["FACE"], "angles": ["PROFILE"], "with": []}
    found = corpus.retrieve(aster.id, need, limit=4)
    picked = found["observations"]
    assert picked[0]["id"] == str(anchor.id) and "production anchor" in picked[0]["why"]
    assert all(o["source_kind"] != "FAN_ART" for o in picked), "supplemental excluded by default"
    assert {o["source_label"].split(" p")[0] for o in picked[1:]} == {
        "Chapter 1",
        "Chapter 2",
        "Chapter 3",
    }
    assert all("candidate - not confirmed to show the character" in o["why"] for o in picked[1:])
    assert corpus.retrieve(aster.id, need, include_candidates=False)["observations"] == [picked[0]]

    # A person confirms what two pages show.
    corpus.review(
        rows["Chapter 2 p2"].id, {"status": "CONFIRMED", "facets": ["FACE"], "angle": "PROFILE"}
    )
    corpus.review(
        rows["Chapter 3 p2"].id,
        {
            "status": "CONFIRMED",
            "facets": ["FACE", "BODY"],
            "angle": "THREE_QUARTER_LEFT",
            "expression": "Smile",
        },
    )
    session.commit()
    ready = corpus.readiness(aster.id)
    assert ready["groups"]["face"] == {
        **ready["groups"]["face"],
        "state": "READY",
        "confirmed_high_authority": 3,
        "distinct_sources": 3,
    }
    assert ready["groups"]["face"]["missing_angles"] == ["FRONT", "THREE_QUARTER_RIGHT", "BACK"]
    assert ready["groups"]["body"]["state"] == "PARTIAL" and ready["grounded"] is True
    ranked = corpus.retrieve(aster.id, {"facets": ["FACE"], "angles": ["PROFILE"]}, limit=3)
    assert ranked["observations"][1]["source_label"] == "Chapter 2 p2"
    assert "angle profile" in ranked["observations"][1]["why"]
    smile = corpus.retrieve(aster.id, {"facets": ["FACE"], "expressions": ["smile"]}, limit=2)
    assert any("expression smile" in o["why"] for o in smile["observations"])

    # An atypical drawing is kept as evidence and stops counting.
    corpus.review(rows["Chapter 3 p2"].id, {"atypical": True})
    assert corpus.readiness(aster.id)["groups"]["face"]["state"] == "PARTIAL"

    # Refreshing adds nothing twice and keeps every review.
    again = corpus.refresh(aster.id)
    session.commit()
    assert again["source_pages_added"] == 0 and again["fan_art_added"] == 0
    kept = _by_source(corpus, aster.id)["Chapter 2 p2"]
    assert (kept.status, kept.angle, kept.facets) == ("CONFIRMED", "PROFILE", ["FACE"])

    with pytest.raises(CatalogInputError, match="supplemental"):
        corpus.review(fan.id, {"authority": "PRIMARY_SOURCE"})
    session.rollback()
    with pytest.raises(CatalogInputError, match="confirmed"):
        corpus.review(rows["Chapter 1 p3"].id, {"anchor": True})
    session.rollback()

    assert corpus.image(rows["Chapter 1 p2"].id).mime == "image/webp"
    with pytest.raises(CatalogNotFoundError):
        corpus.image(rows["Chapter 2 p3"].id)
    assert corpus.image(anchor.id).mime == "image/webp"

    # Co-occurrence: a page swept for both characters helps relative scale.
    beryl_summary = corpus.refresh(beryl.id)
    session.commit()
    assert beryl_summary["source_pages_added"] == 6, "series named by the profile title"
    both = corpus.retrieve(aster.id, {"facets": ["SCALE"], "with": ["Beryl"]}, limit=6)
    assert any(
        "shows the other characters on this page too" in o["why"] for o in both["observations"]
    )

    # A page taken as an environment reference.
    environment = corpus.tag_environment(
        _by_source(corpus, aster.id)["Chapter 1 p2"].id, ["Forest", "night"]
    )
    session.commit()
    manga = MangaProduction(RoughProduction(session, catalog), ProjectLibrary([]))
    matched = manga._environment_references(["forest"], limit=4)
    assert [m["reference_id"] for m in matched] == [str(environment.id)]
    assert matched[0]["matched"] == ["forest"]
    assert face.id != environment.id


def test_original_character_is_grounded_by_the_creator(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    rowan = catalog.create_character(
        "Rowan", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key=rough.PROJECT
    )
    catalog.update_character(
        rowan.id, rowan.row_version, notes="Early season: NO GLASSES\nWardrobe provisional"
    )

    def upload(seed: int, label: str, preferred: bool) -> Any:
        return catalog.add_upload(
            picture(seed),
            ReferenceSpec(
                reference_class=ReferenceClass.CANON,
                origin=ReferenceOrigin.USER_CREATED,
                label=label,
                characters=(
                    CharacterLink(rowan.id, CharacterAspect.FACE, preferred=preferred),
                    CharacterLink(rowan.id, CharacterAspect.FULL_BODY, preferred=preferred),
                ),
            ),
        )

    photo = upload(21, "creator photo", False)
    concept = upload(22, "exploratory concept", True)
    catalog.set_uses(concept.id, [ReferenceUse.IDENTITY, ReferenceUse.STYLE])
    _catalog_rows(session)
    session.commit()
    corpus = _corpus(catalog)

    summary = corpus.refresh(rowan.id)
    session.commit()
    assert summary["source_pages_added"] == 0 and "creator" in summary["note"]
    rows = _by_source(corpus, rowan.id)
    assert (rows["creator photo"].authority, rows["creator photo"].role) == (
        "CREATOR_PRIMARY",
        "GROUNDING",
    )
    stylized = rows["exploratory concept"]
    assert (stylized.authority, stylized.role, stylized.anchor) == (
        "PROJECT_CREATED",
        "STYLIZATION",
        False,
    )

    grounding = corpus.grounding(rowan.id)
    assert grounding["grounding"]["identity"] == [str(photo.id)]
    assert grounding["stylization"] == [str(concept.id)]
    found = corpus.retrieve(
        rowan.id, page_needs({"characters": ["Rowan"], "intents": ["close_up"]}, "Rowan")
    )
    assert [o["reference_id"] for o in found["observations"]] == [str(photo.id)]
    assert [o["reference_id"] for o in found["stylization"]] == [str(concept.id)]

    with pytest.raises(CatalogInputError, match="stylization"):
        corpus.review(stylized.id, {"anchor": True})
    session.rollback()
    with pytest.raises(CatalogInputError, match="original character"):
        corpus.review(rows["creator photo"].id, {"authority": "PRIMARY_SOURCE"})
    session.rollback()

    overview = corpus.overview(rowan.id)
    assert overview["forbidden"] == ["Early season: NO GLASSES"]
    assert overview["readiness"]["grounded"] is True
    assert "creator photos ground identity" in overview["grounding_rule"]
    manga = MangaProduction(RoughProduction(session, catalog), ProjectLibrary([]))
    profile = manga.sample_profile(rough.PROJECT, "fake.deterministic-page")
    assert profile.body["character_rules"]["Rowan"]["forbidden_accessories"] == ["glasses"]
    assert profile.body["grammar"]["series"] == []
    assert manga.sample_profile(rough.PROJECT, "fake.deterministic-page").id == profile.id


def test_page_needs_and_setting_tags() -> None:
    page = {
        "characters": ["Aster Vale", "Beryl"],
        "intents": ["close_up", "two_character"],
        "directions": [
            "Aster Vale in profile, smiling softly, sitting on a log.",
            "Beryl stands in the forest behind her at night.",
        ],
    }
    need = page_needs(page, "Aster Vale")
    assert need["facets"] == ["FACE", "EXPRESSION", "BODY", "SCALE"]
    assert need["framing"] == "CLOSE_UP" and need["angles"] == ["PROFILE"]
    assert need["expressions"] == ["smile", "warm"] and need["poses"] == ["sitting"]
    assert need["with"] == ["Beryl"]
    assert setting_tags("They walk the trail through the forest to a flower meadow at sunset") == [
        "forest",
        "flower field",
        "trail",
        "sunset",
    ]
