"""Recurring objects keep their size, and a character can have more than one sheet.

Two continuity failures are covered here. An object that is four centimetres
across in one panel and the size of a hand in the next: fixed by recording the
measurement and telling the renderer, not by hoping a reference image carries
it. And a character who can only ever have one approved outfit sheet: fixed by
naming which outfit a sheet is about.

Everything is synthetic. No object, character or project is named in the code
under test; a prop is a row.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from continuum_core.corpus import ModelSheetKind
from continuum_core.props import PropStatus, PropView, ScaleAnchor
from continuum_core.references import ReferenceClass, ReferenceOrigin
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_production.props import Props, scale_lock
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import clean_domain_tables, picture

pytestmark = pytest.mark.requires_db

PROJECT = rough.PROJECT
world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog


@pytest.fixture(autouse=True)
def _clean(session: Session) -> None:
    clean_domain_tables(session)


def _prop(props: Props, catalog: ReferenceCatalog, **extra: Any) -> Any:
    hero = catalog.create_character("Aster Vale")
    return props.create(
        PROJECT,
        "brooch",
        "engraved brooch",
        character_id=hero.id,
        size={"diameter_mm": 40},
        body_scale={"relative_to": ScaleAnchor.HEAD_WIDTH.value, "ratio": 0.25},
        **extra,
    )


def test_a_prop_records_its_measurement_and_what_it_reads_against(
    session: Session, catalog: ReferenceCatalog
) -> None:
    props = Props(session)
    prop = _prop(props, catalog)
    assert prop.status == PropStatus.DRAFT.value
    lock = scale_lock(prop)
    assert "about across 4 cm" in lock
    assert "0.25x the wearer's head width" in lock


def test_only_an_approved_prop_travels_with_a_render(
    session: Session, catalog: ReferenceCatalog
) -> None:
    """A draft measurement is somebody thinking aloud, not a rule."""
    props = Props(session)
    prop = _prop(props, catalog)
    assert props.for_characters(PROJECT, [prop.character_id]) == []
    props.approve(prop.id, "creator")
    (approved,) = props.for_characters(PROJECT, [prop.character_id])
    assert approved["scale_lock"] == scale_lock(prop)
    assert approved["status"] == "APPROVED"


def test_a_prop_with_nothing_measured_cannot_be_locked(session: Session) -> None:
    props = Props(session)
    prop = props.create(PROJECT, "lantern", "a lantern")
    with pytest.raises(CatalogInputError, match="no measurement to lock"):
        props.approve(prop.id, "creator")


def test_changing_an_approved_measurement_needs_approving_again(
    session: Session, catalog: ReferenceCatalog
) -> None:
    props = Props(session)
    prop = props.approve(_prop(props, catalog).id, "creator")
    props.update(prop.id, size={"diameter_mm": 55})
    assert prop.status == PropStatus.DRAFT.value
    assert props.for_characters(PROJECT, [prop.character_id]) == []


def test_prop_references_are_filed_by_what_they_show(
    session: Session, catalog: ReferenceCatalog
) -> None:
    props = Props(session)
    prop = _prop(props, catalog)
    plate = catalog.add_upload(
        picture(41),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            label="the brooch beside a hand",
        ),
    )
    props.add_reference(prop.id, plate.id, PropView.SCALE, notes="beside a hand")
    with pytest.raises(CatalogConflictError, match="already shows this prop"):
        props.add_reference(prop.id, plate.id, PropView.SCALE)
    props.add_reference(prop.id, plate.id, PropView.DETAIL)
    views = {link.view for link in props.references(prop.id)}
    assert views == {"SCALE", "DETAIL"}


def test_two_projects_can_use_the_same_prop_key(session: Session) -> None:
    props = Props(session)
    props.create(PROJECT, "brooch", "one project's brooch")
    other = props.create("another-project", "brooch", "another project's brooch")
    assert other.project_key == "another-project"
    with pytest.raises(CatalogConflictError, match="already has a prop"):
        props.create(PROJECT, "brooch", "a duplicate")


def test_a_prop_key_is_a_slug_and_a_ratio_has_bounds(session: Session) -> None:
    props = Props(session)
    with pytest.raises(CatalogInputError, match="lowercase letters"):
        props.create(PROJECT, "Not A Slug", "x")
    with pytest.raises(CatalogInputError, match="ratio must be between"):
        props.create(
            PROJECT,
            "ring",
            "a ring",
            body_scale={"relative_to": ScaleAnchor.HAND_LENGTH.value, "ratio": 900},
        )
    with pytest.raises(CatalogInputError, match="millimetres"):
        props.create(PROJECT, "staff", "a staff", size={"length_mm": -3})


def test_sheet_kinds_that_have_variants_must_name_one() -> None:
    """An outfit sheet is about one outfit; a prop sheet about one prop."""
    from continuum_production.model_builder import SHEET_EVIDENCE, SHEET_VIEWS, VARIANT_KINDS

    assert VARIANT_KINDS == {ModelSheetKind.OUTFIT, ModelSheetKind.ACCESSORY_SCALE}
    for kind in ModelSheetKind:
        assert kind in SHEET_VIEWS and kind in SHEET_EVIDENCE
    # The manga translation is its own question, grounded in who the person is.
    wanted, required = SHEET_EVIDENCE[ModelSheetKind.MANGA_TRANSLATION]
    assert required == "IDENTITY" and "BODY" in wanted
    # A prop scale sheet is never grounded in identity alone.
    assert SHEET_EVIDENCE[ModelSheetKind.ACCESSORY_SCALE][1] == "ACCESSORY"


def test_a_retired_prop_stops_travelling(session: Session, catalog: ReferenceCatalog) -> None:
    props = Props(session)
    prop = props.approve(_prop(props, catalog).id, "creator")
    assert props.for_characters(PROJECT, [prop.character_id])
    props.retire(prop.id)
    assert props.for_characters(PROJECT, [prop.character_id]) == []


def test_props_are_listed_per_project_with_their_locks(
    session: Session, catalog: ReferenceCatalog
) -> None:
    props = Props(session)
    _prop(props, catalog)
    listed = props.all(PROJECT)
    assert [row["prop_key"] for row in listed] == ["brooch"]
    assert listed[0]["body_scale"]["relative_to"] == "HEAD_WIDTH"
    assert props.all("another-project") == []
    assert uuid.UUID(listed[0]["id"])
