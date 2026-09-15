"""W1 acceptance: production models are versioned, human-approved identity locks."""

from __future__ import annotations

import pytest
from continuum_core.corpus import ProductionEvidenceRole
from continuum_db.models import CharacterObservation
from continuum_library import CatalogConflictError, CatalogInputError, ReferenceCatalog
from continuum_production.character_models import CharacterModels
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World

pytestmark = pytest.mark.requires_db
session = rough.session
catalog = rough.catalog
world = rough.world


def _observation(
    session: Session,
    character_id,
    *,
    locator: str,
    facet: str,
    authority: str = "PRIMARY_SOURCE",
    role: str = "GROUNDING",
    status: str = "CONFIRMED",
) -> CharacterObservation:
    row = CharacterObservation(
        character_id=character_id,
        locator=locator,
        source_kind="SOURCE_PAGE",
        unit_key=f"unit-{locator}",
        page_offset=0,
        series_key="invented-series",
        source_label=locator,
        authority=authority,
        status=status,
        role=role,
        facets=[facet],
        evidence={},
    )
    session.add(row)
    session.flush()
    return row


def test_versions_require_human_approval_and_supersede(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    character = catalog.create_character("Juniper Quill", source_label="Invented Almanac")
    face = _observation(session, character.id, locator="identity-page", facet="FACE")
    body = _observation(session, character.id, locator="body-page", facet="BODY")
    models = CharacterModels(session)

    first = models.create(
        "sample-project",
        character.id,
        name="Primary turnarounds",
        identity_rules=["crescent fringe"],
        restrictions=["no spectacles"],
    )
    models.add_evidence(
        first.id, face.id, ProductionEvidenceRole.IDENTITY, preferred=True, position=0
    )
    models.add_evidence(first.id, body.id, ProductionEvidenceRole.BODY, required=True, position=1)
    assert models.active("sample-project", character.id) is None
    models.submit(first.id)
    with pytest.raises(CatalogInputError, match="human reviewer"):
        models.approve(first.id, "")
    models.approve(first.id, "studio lead")
    assert models.active("sample-project", character.id).id == first.id

    second = models.create("sample-project", character.id, name="Refined turnarounds")
    assert second.version == 2 and second.status == "DRAFT"
    models.add_evidence(second.id, face.id, ProductionEvidenceRole.IDENTITY)
    models.submit(second.id)
    models.approve(second.id, "studio lead")
    assert first.status == "SUPERSEDED"
    assert models.active("sample-project", character.id).id == second.id
    assert [
        entry["role"] for entry in models.bundle("sample-project", character.id)["evidence"]
    ] == ["IDENTITY"]


def test_candidate_and_stylization_cannot_define_identity(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    character = catalog.create_character("Kestrel Moss", source_label="Invented Almanac")
    candidate = _observation(
        session, character.id, locator="candidate-page", facet="FACE", status="CANDIDATE"
    )
    style = _observation(
        session,
        character.id,
        locator="style-page",
        facet="FACE",
        authority="PROJECT_CREATED",
        role="STYLIZATION",
    )
    model = CharacterModels(session).create("sample-project", character.id, name="Identity lock")
    service = CharacterModels(session)
    with pytest.raises(CatalogInputError, match="Candidate"):
        service.add_evidence(model.id, candidate.id, ProductionEvidenceRole.IDENTITY)
    with pytest.raises(CatalogInputError, match="high-authority grounding"):
        service.add_evidence(model.id, style.id, ProductionEvidenceRole.IDENTITY)
    service.add_evidence(model.id, style.id, ProductionEvidenceRole.EXPRESSION)
    service.submit(model.id)
    service.approve(model.id, "art director")
    with pytest.raises(CatalogConflictError, match="immutable"):
        service.add_evidence(model.id, style.id, ProductionEvidenceRole.POSE)
