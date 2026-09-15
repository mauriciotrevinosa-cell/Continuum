"""W4 acceptance: provider-neutral, reference-grounded character model sheets.

All characters, references and rendered pixels in this test are synthetic.
The renderer is an explicit artwork-candidate test double; the shipped registry
continues to report the real backend gap truthfully.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from continuum_core import ProviderUnavailableError
from continuum_core.corpus import ModelSheetKind, ModelSheetStatus, ProductionEvidenceRole
from continuum_core.references import (
    CharacterAspect,
    CharacterOrigin,
    ReferenceClass,
    ReferenceOrigin,
    RenderOutput,
)
from continuum_db.models import CharacterModelSheetAttempt, Job, ReferenceItem
from continuum_library import CharacterLink, ReferenceCatalog, ReferenceSpec
from continuum_production.character_models import CharacterModels
from continuum_production.corpus import CharacterCorpus
from continuum_production.model_builder import SHEET_VIEWS, CharacterModelBuilder
from continuum_providers import (
    Capability,
    CostClass,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
    ProviderRegistry,
)
from continuum_providers.artwork import (
    CharacterSheetRequest,
    CharacterSheetResult,
    RenderedImage,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.acceptance import test_phase1_rough_production as rough
from tests.phase1_world import World, picture, snapshot

pytestmark = pytest.mark.requires_db
world = rough.world
settings = rough.settings
session = rough.session
catalog = rough.catalog
worker = rough.worker

PROJECT = "model-builder-project"


@dataclass
class CharacterSheetDouble:
    descriptor = ProviderDescriptor(
        id="fake.character-sheet-artwork",
        capabilities=frozenset({Capability.CHARACTER_MODEL_RENDER}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref="synthetic-character-sheet-double",
        version="1",
        license_note="Test-only synthetic renderer.",
        rough_output=RenderOutput.ARTWORK_CANDIDATE,
    )

    def render_character_sheet(self, request: CharacterSheetRequest) -> CharacterSheetResult:
        data = picture(request.seed)
        return CharacterSheetResult(
            provider_id=self.descriptor.id,
            output=RenderOutput.ARTWORK_CANDIDATE,
            image=RenderedImage(data=data, mime="image/png", width=240, height=320),
            provenance={
                "backend": self.descriptor.id,
                "model": {
                    "name": "synthetic-character-sheet-double",
                    "version": "1",
                    "sha256": "2" * 64,
                    "license": "test-only",
                    "source": "tests/acceptance/test_m3_character_model_builder.py",
                },
                "workflow": {
                    "id": "character-turnaround",
                    "version": "1",
                    "sha256": "3" * 64,
                },
                "settings": {
                    "seed": request.seed,
                    "kind": request.sheet_kind,
                    "views": list(request.views),
                    "reference_count": len(request.references),
                },
            },
        )


def _registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(CharacterSheetDouble())
    return registry


def _review_model(session: Session, catalog: ReferenceCatalog) -> tuple[CharacterModels, object]:
    character = catalog.create_character(
        "Iris Vale", origin=CharacterOrigin.PROJECT_ORIGINAL, project_key=PROJECT
    )
    catalog.add_upload(
        picture(31),
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.USER_CREATED,
            label="creator identity and body turnaround",
            characters=(
                CharacterLink(character.id, CharacterAspect.FACE, preferred=True),
                CharacterLink(character.id, CharacterAspect.FULL_BODY, preferred=True),
            ),
        ),
    )
    corpus = CharacterCorpus(session, catalog)
    corpus.sync_curated(character.id)
    observation = corpus.observations(character.id)[0]
    models = CharacterModels(session)
    model = models.create(
        PROJECT,
        character.id,
        name="Iris identity lock",
        identity_rules=["asymmetric fringe", "round pupils"],
        restrictions=["no glasses"],
    )
    models.add_evidence(model.id, observation.id, ProductionEvidenceRole.IDENTITY, preferred=True)
    models.add_evidence(model.id, observation.id, ProductionEvidenceRole.BODY, required=True)
    models.submit(model.id)
    return models, model


def test_head_and_full_body_jobs_are_grounded_reviewable_and_versioned(
    session: Session,
    catalog: ReferenceCatalog,
    world: World,
    worker,
) -> None:
    vault_before = snapshot(world.vault)
    models, model = _review_model(session, catalog)
    corpus = CharacterCorpus(session, catalog)
    registry = _registry()
    builder = CharacterModelBuilder(session, catalog, registry, corpus)
    assert builder.readiness() == {
        "ready": True,
        "provider_id": "fake.character-sheet-artwork",
        "blocked_reason": None,
        "remediation": {"message": "Configure a reference-conditioning character-sheet provider."},
    }

    head = builder.request(model.id, ModelSheetKind.HEAD, seed=41)
    body = builder.request(model.id, ModelSheetKind.FULL_BODY, seed=42)
    assert tuple(head.views) == SHEET_VIEWS[ModelSheetKind.HEAD]
    assert tuple(body.views) == SHEET_VIEWS[ModelSheetKind.FULL_BODY]
    assert {item["role"] for item in head.reference_pack} == {"IDENTITY"}
    assert {item["role"] for item in body.reference_pack} == {"IDENTITY", "BODY"}
    session.commit()

    worker.providers = registry
    worker.resource_classes = [*worker.resource_classes, "gpu"]
    assert rough.drain(worker) == 2
    session.expire_all()
    head = session.get(CharacterModelSheetAttempt, head.id)
    body = session.get(CharacterModelSheetAttempt, body.id)
    jobs = [session.get(Job, head.job_id), session.get(Job, body.job_id)]
    assert head.status == body.status == ModelSheetStatus.GENERATED.value, [
        (job.status, job.last_error.get("message"), job.last_error.get("technical_detail"))
        for job in jobs
    ]
    assert head.provenance["workflow"]["id"] == "character-turnaround"
    generated = session.get(ReferenceItem, head.reference_id)
    assert generated.origin is ReferenceOrigin.GENERATED
    assert generated.visual_origin == "PROJECT_CREATED"
    assert snapshot(world.vault) == vault_before

    reviewed_body, body_model, regenerated = builder.review(
        body.id, "APPROVE", "art director", "silhouette accepted"
    )
    assert reviewed_body.status == ModelSheetStatus.APPROVED.value
    assert regenerated is None
    assert body_model.status == "DRAFT" and body_model.approved_by is None
    assert body_model.body_sheet_reference_id == body.reference_id

    rejected_head, no_model, replacement = builder.review(
        head.id, "REGENERATE", "art director", "adjust hair volume"
    )
    assert rejected_head.status == ModelSheetStatus.REJECTED.value
    assert no_model is None
    assert replacement.parent_attempt_id == head.id and replacement.seed == 42
    session.commit()
    assert rough.drain(worker) == 1
    session.expire_all()

    replacement = session.get(CharacterModelSheetAttempt, replacement.id)
    reviewed_head, head_model, no_replacement = builder.review(
        replacement.id, "APPROVE", "art director"
    )
    assert reviewed_head.status == ModelSheetStatus.APPROVED.value
    assert no_replacement is None
    assert head_model.version == body_model.version + 1
    assert head_model.status == "DRAFT" and head_model.approved_at is None
    assert head_model.head_sheet_reference_id == replacement.reference_id
    assert head_model.body_sheet_reference_id == body.reference_id
    assert len(models.evidence(head_model.id)) == 2


def test_missing_backend_is_truthful_and_queues_nothing(
    session: Session, catalog: ReferenceCatalog, world: World
) -> None:
    _models, model = _review_model(session, catalog)
    builder = CharacterModelBuilder(
        session, catalog, ProviderRegistry(), CharacterCorpus(session, catalog)
    )
    readiness = builder.readiness()
    assert readiness["ready"] is False
    assert readiness["blocked_reason"] == "MISSING_PROVIDER"
    before = session.scalar(select(func.count()).select_from(CharacterModelSheetAttempt))
    with pytest.raises(ProviderUnavailableError, match="No provider offers"):
        builder.request(model.id, ModelSheetKind.HEAD)
    after = session.scalar(select(func.count()).select_from(CharacterModelSheetAttempt))
    assert after == before
