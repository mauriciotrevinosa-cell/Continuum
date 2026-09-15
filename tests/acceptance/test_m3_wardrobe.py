"""M3 W6: timeline-aware wardrobe - identity and clothing stay separate.

Pinned with invented characters:

* a project-created outfit has a human review state and never self-approves;
* a source outfit is not reviewed (its state is source-faithful);
* a garment has an owner and may be worn by a different character in a
  specific project/story stage; borrowing never clones identity;
* a later assignment never rewrites an earlier one (append-only), so a
  borrowed garment never becomes the wearer's default historical outfit;
* wardrobe resolution keeps owner and wearer apart and flags borrowing.

All content is invented (D-18 / A-05).
"""

from __future__ import annotations

import pytest
from continuum_core.references import CharacterOrigin, OutfitKind
from continuum_library import CatalogConflictError, CatalogInputError, ReferenceCatalog
from continuum_production.wardrobe import Wardrobe
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World

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

    # Mau owns and wears it at arrival.
    wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "EARLY_ARRIVAL")
    # Frieren borrows the SAME garment in E14 and E18.
    wardrobe.assign_wear(
        hoodie.id, frieren.id, "the-arrivals", "E14", context="borrowed after reconciliation"
    )
    wardrobe.assign_wear(
        hoodie.id, frieren.id, "the-arrivals", "E18", context="chocolate callback"
    )

    # The owner is still Mau; the wearer is Frieren; borrowing is flagged.
    resolved = wardrobe.resolve("the-arrivals", frieren.id, "E14")
    assert resolved is not None
    assert resolved["owner_character_id"] == str(mau.id)
    assert resolved["wearer_character_id"] == str(frieren.id)
    assert resolved["borrowed"] is True
    assert resolved["name"] == "M-H1 McLaren hoodie"

    # Mau's own arrival resolution is unchanged by the later borrowing.
    arrival = wardrobe.resolve("the-arrivals", mau.id, "EARLY_ARRIVAL")
    assert arrival is not None
    assert arrival["owner_character_id"] == str(mau.id)
    assert arrival["wearer_character_id"] == str(mau.id)
    assert arrival["borrowed"] is False

    # A conflicting wearer for the same stage is refused, not silently rewritten.
    with pytest.raises(CatalogConflictError, match="different wearer"):
        wardrobe.assign_wear(hoodie.id, mau.id, "the-arrivals", "E14")

    # Re-recording the same input is a no-op (deterministic upsert).
    again = wardrobe.assign_wear(hoodie.id, frieren.id, "the-arrivals", "E14")
    assert again.wearer_character_id == frieren.id