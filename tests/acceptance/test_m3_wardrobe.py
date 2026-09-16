"""M3 W6: timeline-aware wardrobe - identity and clothing stay separate.

Pinned with invented characters:

* a project-created outfit has a human review state and never self-approves;
* a source outfit is not reviewed (its state is source-faithful);
* a garment has an owner and may be worn by a different character in a
  specific project/story stage; borrowing never clones identity;
* a later assignment never rewrites an earlier one (append-only), so a
  borrowed garment never becomes the wearer's default historical outfit;
* wardrobe resolution keeps owner and wearer apart and flags borrowing;
* a character may wear several garments at once in a stage, so resolution
  returns a set, not one arbitrary outfit;
* a garment's condition is stage-scoped on the wear assignment, so
  clean -> dirty -> damaged -> repaired survives without rewriting identity;
* only an APPROVED project-created outfit resolves into production wardrobe;
* a PROJECT outfit cannot be worn in a different project;
* an outfit model-sheet reference has a human-controlled attach path.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import uuid

import pytest
from continuum_core.references import CharacterOrigin, OutfitKind, ReferenceClass, ReferenceOrigin
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_production.wardrobe import Wardrobe
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World, picture

pytestmark = pytest.mark.requires_db

session = rough.session
catalog = rough.catalog
world = rough.world


def test_project_outfit_review_never_self_approves(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    wardrobe = Wardrobe(session)
    assert hoodie.review_status is None

    with pytest.raises(CatalogInputError, match="human reviewer"):
        wardrobe.review(hoodie.id, "APPROVED", "")
    wardrobe.review(hoodie.id, "REVIEW", "art director")
    assert hoodie.review_status == "REVIEW"
    wardrobe.review(hoodie.id, "APPROVED", "art director")
    assert hoodie.review_status == "APPROVED"
    assert hoodie.reviewed_by == "art director"
    assert hoodie.reviewed_at is not None


def test_source_outfit_is_not_reviewed(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    frieren = catalog.create_character("Frieren", source_label="Invented Almanac")
    robes = catalog.create_outfit(frieren.id, "Travelling robes", kind=OutfitKind.SOURCE_DEFAULT)
    with pytest.raises(CatalogConflictError, match="project-created"):
        Wardrobe(session).review(robes.id, "APPROVED", "art director")


def test_borrowed_garment_keeps_owner_and_never_rewrites_history(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    frieren = catalog.create_character("Frieren", source_label="Invented Almanac")
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    wardrobe = Wardrobe(session)
    wardrobe.review(hoodie.id, "APPROVED", "art director")

    # Mau owns and wears it at arrival.
    wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "EARLY_ARRIVAL")
    # Frieren borrows the SAME garment in E14 and E18.
    wardrobe.assign_wear(
        hoodie.id, frieren.id, "the-arrivals", "E14", context="borrowed after reconciliation"
    )
    wardrobe.assign_wear(hoodie.id, frieren.id, "the-arrivals", "E18", context="chocolate callback")

    # The owner is still Mau; the wearer is Frieren; borrowing is flagged.
    resolved = wardrobe.resolve("the-arrivals", frieren.id, "E14")
    assert len(resolved) == 1
    assert resolved[0]["owner_character_id"] == str(mau.id)
    assert resolved[0]["wearer_character_id"] == str(frieren.id)
    assert resolved[0]["borrowed"] is True
    assert resolved[0]["name"] == "M-H1 McLaren hoodie"

    # Mau's own arrival resolution is unchanged by the later borrowing.
    arrival = wardrobe.resolve("the-arrivals", mau.id, "EARLY_ARRIVAL")
    assert len(arrival) == 1
    assert arrival[0]["owner_character_id"] == str(mau.id)
    assert arrival[0]["wearer_character_id"] == str(mau.id)
    assert arrival[0]["borrowed"] is False

    # A conflicting wearer for the same stage is refused, not silently rewritten.
    with pytest.raises(CatalogConflictError, match="different wearer"):
        wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "E14")

    # Re-recording the same input is a no-op (deterministic upsert).
    again = wardrobe.assign_wear(hoodie.id, frieren.id, "the-arrivals", "E14")
    assert again.wearer_character_id == frieren.id


def test_multiple_garments_per_stage(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    frieren = catalog.create_character("Frieren", source_label="Invented Almanac")
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    cap = catalog.create_outfit(
        mau.id, "M-A2 McLaren cap", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    bottoms = catalog.create_outfit(
        frieren.id, "Comfortable bottoms", kind=OutfitKind.SOURCE_DEFAULT
    )
    wardrobe = Wardrobe(session)
    wardrobe.review(hoodie.id, "APPROVED", "art director")
    wardrobe.review(cap.id, "APPROVED", "art director")

    # In E18 Frieren wears Mau's hoodie, Mau's cap and her own bottoms at once.
    wardrobe.assign_wear(hoodie.id, frieren.id, "the-arrivals", "E18")
    wardrobe.assign_wear(cap.id, frieren.id, "the-arrivals", "E18")
    wardrobe.assign_wear(bottoms.id, frieren.id, "the-arrivals", "E18")

    resolved = wardrobe.resolve("the-arrivals", frieren.id, "E18")
    names = {item["name"] for item in resolved}
    assert names == {"M-H1 McLaren hoodie", "M-A2 McLaren cap", "Comfortable bottoms"}

    # Owner and wearer are preserved per garment; borrowing is flagged per garment.
    by_name = {item["name"]: item for item in resolved}
    assert by_name["M-H1 McLaren hoodie"]["owner_character_id"] == str(mau.id)
    assert by_name["M-H1 McLaren hoodie"]["borrowed"] is True
    assert by_name["M-A2 McLaren cap"]["owner_character_id"] == str(mau.id)
    assert by_name["M-A2 McLaren cap"]["borrowed"] is True
    assert by_name["Comfortable bottoms"]["owner_character_id"] == str(frieren.id)
    assert by_name["Comfortable bottoms"]["borrowed"] is False


def test_garment_condition_is_stage_scoped(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    wardrobe = Wardrobe(session)
    wardrobe.review(hoodie.id, "APPROVED", "art director")

    wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "EARLY_ARRIVAL", condition="clean")
    wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "E14", condition="dirty/travel-worn")
    wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "E20", condition="damaged")
    wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "E22", condition="repaired/patched")

    # The same garment identity survives across states; only the stage-scoped
    # condition changes.
    stages = {
        item["stage"]: item
        for item in (
            wardrobe.resolve("the-arrivals", mau.id, "EARLY_ARRIVAL")
            + wardrobe.resolve("the-arrivals", mau.id, "E14")
            + wardrobe.resolve("the-arrivals", mau.id, "E20")
            + wardrobe.resolve("the-arrivals", mau.id, "E22")
        )
    }
    assert stages["EARLY_ARRIVAL"]["condition"] == "clean"
    assert stages["E14"]["condition"] == "dirty/travel-worn"
    assert stages["E20"]["condition"] == "damaged"
    assert stages["E22"]["condition"] == "repaired/patched"
    assert {stages[s]["outfit_id"] for s in stages} == {str(hoodie.id)}


def test_unapproved_project_outfit_does_not_resolve(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    wardrobe = Wardrobe(session)

    # A project-created outfit begins unreviewed and must not resolve.
    assert hoodie.review_status is None
    assert wardrobe.resolve("the-arrivals", mau.id, "EARLY_ARRIVAL") == []

    # A DRAFT or REVIEW project outfit still does not resolve.
    wardrobe.review(hoodie.id, "REVIEW", "art director")
    assert wardrobe.resolve("the-arrivals", mau.id, "EARLY_ARRIVAL") == []

    # Only APPROVED resolves into production wardrobe.
    wardrobe.review(hoodie.id, "APPROVED", "art director")
    resolved = wardrobe.resolve("the-arrivals", mau.id, "EARLY_ARRIVAL")
    assert len(resolved) == 1
    assert resolved[0]["name"] == "M-H1 McLaren hoodie"


def test_cross_project_wear_is_rejected(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    wardrobe = Wardrobe(session)

    with pytest.raises(CatalogConflictError, match="own project"):
        wardrobe.assign_wear(hoodie.id, mau.id, "other-project", "E14")


def test_model_sheet_attachment(session: Session, catalog: ReferenceCatalog, world: World) -> None:
    mau = catalog.create_character(
        "Mau", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key="the-arrivals"
    )
    hoodie = catalog.create_outfit(
        mau.id, "M-H1 McLaren hoodie", kind=OutfitKind.PROJECT, project_key="the-arrivals"
    )
    sheet = catalog.add_upload(
        picture(7),
        ReferenceSpec(reference_class=ReferenceClass.CANON, origin=ReferenceOrigin.USER_CREATED),
    )
    wardrobe = Wardrobe(session)

    assert hoodie.model_sheet_reference_id is None
    wardrobe.attach_model_sheet(hoodie.id, sheet.id)
    assert hoodie.model_sheet_reference_id == sheet.id

    # A missing reference is refused.
    with pytest.raises(Exception, match="reference does not exist"):
        wardrobe.attach_model_sheet(hoodie.id, uuid.uuid4())
