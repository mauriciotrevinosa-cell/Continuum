"""Provider-neutral, reference-grounded character model-sheet jobs (M3 W4)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core.corpus import ModelSheetKind, ModelSheetStatus, ProductionEvidenceRole
from continuum_core.references import (
    AssetMedium,
    AssetOrigin,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
    RenderOutput,
)
from continuum_db.models import (
    CharacterModelSheetAttempt,
    CharacterObservation,
    CharacterProductionModel,
    Job,
)
from continuum_jobs import enqueue
from continuum_library import (
    CatalogConflictError,
    CatalogInputError,
    CatalogNotFoundError,
    ReferenceCatalog,
    ReferenceSpec,
)
from continuum_providers import Capability, DataClass, ProviderRegistry
from continuum_providers.artwork import (
    ArtworkReference,
    CharacterSheetProvider,
    CharacterSheetRequest,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from continuum_production.character_models import CharacterModels
from continuum_production.corpus import CharacterCorpus

MODEL_SHEET_JOB_TYPE = "visual.character_model_sheet"
MODEL_SHEET_RECIPE = "continuum.character-sheet/1"
SHEET_VIEWS = {
    ModelSheetKind.HEAD: ("FRONT", "THREE_QUARTER", "PROFILE", "BACK_HAIR"),
    ModelSheetKind.FULL_BODY: ("FRONT", "THREE_QUARTER", "SIDE", "BACK"),
}


def attempt_view(row: CharacterModelSheetAttempt, job: Job | None = None) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "model_id": str(row.model_id),
        "project_key": row.project_key,
        "character_id": str(row.character_id),
        "sheet_kind": row.sheet_kind,
        "attempt": row.attempt,
        "status": row.status,
        "seed": row.seed,
        "views": row.views,
        "reference_count": len(row.reference_pack),
        "reference_id": str(row.reference_id) if row.reference_id else None,
        "provenance": row.provenance,
        "reviewed_by": row.reviewed_by,
        "review_notes": row.review_notes,
        "job": {
            "id": str(job.id),
            "status": job.status.value,
            "blocked_reason": job.blocked_reason.value if job.blocked_reason else None,
            "remediation": job.remediation,
        }
        if job
        else None,
        "image": f"/library/character-model-sheet-attempts/{row.id}/image"
        if row.content_hash
        else None,
    }


class CharacterModelBuilder:
    def __init__(
        self,
        session: Session,
        catalog: ReferenceCatalog,
        providers: ProviderRegistry,
        corpus: CharacterCorpus,
    ):
        self.session, self.catalog, self.providers, self.corpus = (
            session,
            catalog,
            providers,
            corpus,
        )

    def readiness(self) -> dict[str, Any]:
        decision = self.providers.evaluate(
            Capability.CHARACTER_MODEL_RENDER, DataClass.SOURCE_EXCERPT
        )
        if decision.permitted and decision.provider_id:
            provider = self.providers.get(decision.provider_id)
            if not isinstance(provider, CharacterSheetProvider):
                return {
                    "ready": False,
                    "provider_id": decision.provider_id,
                    "blocked_reason": "MISSING_PROVIDER",
                    "remediation": {
                        "message": "The selected provider does not implement character sheets.",
                        "action": "Configure a provider with the character-sheet contract.",
                    },
                }
        return {
            "ready": decision.permitted,
            "provider_id": decision.provider_id,
            "blocked_reason": decision.blocked_reason.value if decision.blocked_reason else None,
            "remediation": decision.remediation
            or {"message": "Configure a reference-conditioning character-sheet provider."},
        }

    def attempts(self, project_key: str, character_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.session.execute(
            select(CharacterModelSheetAttempt)
            .where(
                CharacterModelSheetAttempt.project_key == project_key,
                CharacterModelSheetAttempt.character_id == character_id,
            )
            .order_by(CharacterModelSheetAttempt.created_at.desc())
        ).scalars()
        return [
            attempt_view(row, self.session.get(Job, row.job_id) if row.job_id else None)
            for row in rows
        ]

    def request(
        self,
        model_id: uuid.UUID,
        sheet_kind: ModelSheetKind,
        *,
        seed: int = 1,
        parent: CharacterModelSheetAttempt | None = None,
    ) -> CharacterModelSheetAttempt:
        model = self.session.get(CharacterProductionModel, model_id)
        if model is None:
            raise CatalogNotFoundError("That production model does not exist.")
        if model.status not in {"REVIEW", "APPROVED"}:
            raise CatalogConflictError(
                "Submit the evidence-backed model for review before building sheets."
            )
        provider = self.providers.resolve(
            Capability.CHARACTER_MODEL_RENDER, DataClass.SOURCE_EXCERPT
        )
        if not isinstance(provider, CharacterSheetProvider):
            raise CatalogInputError(
                "The selected provider does not implement the character-sheet contract."
            )
        wanted = {ProductionEvidenceRole.IDENTITY.value}
        if sheet_kind is ModelSheetKind.FULL_BODY:
            wanted |= {ProductionEvidenceRole.BODY.value, ProductionEvidenceRole.WARDROBE.value}
        links = [
            link for link in CharacterModels(self.session).evidence(model.id) if link.role in wanted
        ]
        observations = (
            {
                row.id: row
                for row in self.session.execute(
                    select(CharacterObservation).where(
                        CharacterObservation.id.in_([link.observation_id for link in links]),
                        CharacterObservation.status == "CONFIRMED",
                    )
                ).scalars()
            }
            if links
            else {}
        )
        pack = []
        for link in links:
            observation = observations.get(link.observation_id)
            if observation is None:
                continue
            resolved = self.corpus.resolve(observation)
            if resolved:
                pack.append(
                    {
                        "observation_id": str(observation.id),
                        "reference_id": str(resolved[1]) if resolved[1] else None,
                        "locator": resolved[0],
                        "role": link.role,
                        "authority": observation.authority,
                        "facets": observation.facets,
                    }
                )
        required = "IDENTITY" if sheet_kind is ModelSheetKind.HEAD else "BODY"
        if not any(item["role"] == required for item in pack):
            raise CatalogInputError(
                f"A {sheet_kind.value} sheet needs confirmed {required.lower()} evidence."
            )
        number = (
            self.session.execute(
                select(func.max(CharacterModelSheetAttempt.attempt)).where(
                    CharacterModelSheetAttempt.model_id == model.id,
                    CharacterModelSheetAttempt.sheet_kind == sheet_kind.value,
                )
            ).scalar_one()
            or 0
        ) + 1
        row = CharacterModelSheetAttempt(
            model_id=model.id,
            character_id=model.character_id,
            project_key=model.project_key,
            sheet_kind=sheet_kind.value,
            attempt=number,
            parent_attempt_id=parent.id if parent else None,
            status=ModelSheetStatus.QUEUED.value,
            seed=seed,
            views=list(SHEET_VIEWS[sheet_kind]),
            reference_pack=pack,
            rules={
                "identity": model.identity_rules,
                "restrictions": model.restrictions,
                "active_outfit_id": str(model.active_outfit_id) if model.active_outfit_id else None,
            },
        )
        self.session.add(row)
        self.session.flush()
        job, _ = enqueue(
            self.session,
            MODEL_SHEET_JOB_TYPE,
            payload={"attempt_id": str(row.id)},
            resource_class="gpu",
            max_attempts=3,
            recipe_version=MODEL_SHEET_RECIPE,
        )
        row.job_id = job.id
        self.session.flush()
        return row

    def review(
        self, attempt_id: uuid.UUID, decision: str, reviewer: str, notes: str = ""
    ) -> tuple[
        CharacterModelSheetAttempt,
        CharacterProductionModel | None,
        CharacterModelSheetAttempt | None,
    ]:
        row = self.session.get(CharacterModelSheetAttempt, attempt_id)
        if row is None:
            raise CatalogNotFoundError("That model-sheet attempt does not exist.")
        if row.status != ModelSheetStatus.GENERATED.value:
            raise CatalogConflictError("Only a generated candidate can be reviewed.")
        reviewer = reviewer.strip()
        if not reviewer:
            raise CatalogInputError("A human reviewer is required.")
        if decision not in {"APPROVE", "REJECT", "REGENERATE"}:
            raise CatalogInputError("Decision must be APPROVE, REJECT or REGENERATE.")
        row.reviewed_by, row.review_notes, row.reviewed_at = (
            reviewer,
            notes[:4000],
            dt.datetime.now(dt.UTC),
        )
        if decision == "REJECT":
            row.status = ModelSheetStatus.REJECTED.value
            self.session.flush()
            return row, None, None
        if decision == "REGENERATE":
            row.status = ModelSheetStatus.REJECTED.value
            regenerated = self.request(
                row.model_id, ModelSheetKind(row.sheet_kind), seed=row.seed + 1, parent=row
            )
            return row, None, regenerated
        row.status = ModelSheetStatus.APPROVED.value
        previously_approved = self.session.execute(
            select(CharacterModelSheetAttempt).where(
                CharacterModelSheetAttempt.project_key == row.project_key,
                CharacterModelSheetAttempt.character_id == row.character_id,
                CharacterModelSheetAttempt.sheet_kind == row.sheet_kind,
                CharacterModelSheetAttempt.status == ModelSheetStatus.APPROVED.value,
                CharacterModelSheetAttempt.id != row.id,
            )
        ).scalars()
        for previous in previously_approved:
            previous.status = ModelSheetStatus.SUPERSEDED.value
        base = self.session.get(CharacterProductionModel, row.model_id)
        assert base is not None
        counterpart_kind = (
            ModelSheetKind.FULL_BODY.value
            if row.sheet_kind == ModelSheetKind.HEAD.value
            else ModelSheetKind.HEAD.value
        )
        counterpart = self.session.execute(
            select(CharacterModelSheetAttempt)
            .where(
                CharacterModelSheetAttempt.project_key == row.project_key,
                CharacterModelSheetAttempt.character_id == row.character_id,
                CharacterModelSheetAttempt.sheet_kind == counterpart_kind,
                CharacterModelSheetAttempt.status == ModelSheetStatus.APPROVED.value,
            )
            .order_by(CharacterModelSheetAttempt.reviewed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        models = CharacterModels(self.session)
        new = models.create(
            base.project_key,
            base.character_id,
            name=base.name,
            summary=base.summary,
            identity_rules=base.identity_rules,
            restrictions=base.restrictions,
            active_outfit_id=base.active_outfit_id,
            head_sheet_reference_id=row.reference_id
            if row.sheet_kind == "HEAD"
            else (counterpart.reference_id if counterpart else base.head_sheet_reference_id),
            body_sheet_reference_id=row.reference_id
            if row.sheet_kind == "FULL_BODY"
            else (counterpart.reference_id if counterpart else base.body_sheet_reference_id),
            created_from={
                "kind": "model_sheet_approval",
                "attempt_id": str(row.id),
                "reviewer": reviewer,
            },
        )
        for link in models.evidence(base.id):
            models.add_evidence(
                new.id,
                link.observation_id,
                ProductionEvidenceRole(link.role),
                preferred=link.preferred,
                required=link.required,
                position=link.position,
                notes=link.notes,
            )
        self.session.flush()
        return row, new, None


def render_model_sheet(
    session: Session,
    attempt_id: uuid.UUID,
    *,
    catalog: ReferenceCatalog,
    providers: ProviderRegistry,
    corpus: CharacterCorpus,
) -> dict[str, Any]:
    row = session.get(CharacterModelSheetAttempt, attempt_id)
    if row is None:
        raise CatalogNotFoundError("That model-sheet attempt does not exist.")
    if row.content_hash:
        return {"attempt_id": str(row.id), "content_hash": row.content_hash, "rerun": True}
    provider = providers.resolve(Capability.CHARACTER_MODEL_RENDER, DataClass.SOURCE_EXCERPT)
    if not isinstance(provider, CharacterSheetProvider):
        raise CatalogConflictError("The selected provider does not implement character sheets.")
    refs = []
    for item in row.reference_pack:
        observation = corpus.observation(uuid.UUID(item["observation_id"]))
        refs.append(
            ArtworkReference(
                role="CANON",
                reference_id=item["reference_id"] or item["locator"],
                data=corpus.image(observation.id).data,
                character=str(row.character_id),
                facet=item["role"],
                teaches=tuple(item["facets"]),
                provenance={
                    "observation_id": item["observation_id"],
                    "authority": item["authority"],
                    "locator": item["locator"],
                },
            )
        )
    result = provider.render_character_sheet(
        CharacterSheetRequest(
            sheet_kind=row.sheet_kind,
            views=tuple(row.views),
            width=1600,
            height=1000,
            seed=row.seed,
            references=tuple(refs),
            identity_rules=tuple(row.rules["identity"]),
            restrictions=tuple(row.rules["restrictions"]),
            outfit_id=row.rules.get("active_outfit_id"),
            settings={"recipe": MODEL_SHEET_RECIPE},
        )
    )
    if result.output is not RenderOutput.ARTWORK_CANDIDATE:
        raise CatalogInputError("A test render cannot become a model-sheet candidate.")
    provenance = result.provenance or {}
    required = {
        "model": ("name", "version", "sha256", "license", "source"),
        "workflow": ("id", "version", "sha256"),
    }
    missing = [key for key in ("backend", "settings") if not provenance.get(key)]
    for section, keys in required.items():
        values = provenance.get(section) or {}
        missing.extend(f"{section}.{key}" for key in keys if not values.get(key))
    if missing:
        raise CatalogInputError(
            "Model-sheet provenance is not reproducible without " + ", ".join(missing) + "."
        )
    stored = catalog.store_bytes(
        result.image.data,
        root_key="generated",
        medium=AssetMedium.IMAGE,
        origin=AssetOrigin.GENERATED,
    )
    reference = catalog.add_generated(
        stored.content_hash,
        ReferenceSpec(
            reference_class=ReferenceClass.CANON,
            origin=ReferenceOrigin.GENERATED,
            label=f"{row.sheet_kind} model-sheet candidate",
            uses=(ReferenceUse.IDENTITY,),
        ),
        {
            "kind": "character_model_sheet",
            "attempt_id": str(row.id),
            "reference_pack": row.reference_pack,
            "provenance": result.provenance,
        },
    )
    reference.visual_origin = "PROJECT_CREATED"
    row.status, row.reference_id, row.content_hash = (
        ModelSheetStatus.GENERATED.value,
        reference.id,
        stored.content_hash,
    )
    row.mime, row.width, row.height = result.image.mime, result.image.width, result.image.height
    row.provenance, row.generated_at = result.provenance, dt.datetime.now(dt.UTC)
    session.flush()
    return {
        "attempt_id": str(row.id),
        "content_hash": row.content_hash,
        "provider_id": result.provider_id,
        "rerun": False,
    }
