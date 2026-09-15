"""Versioned project character production models and human approval workflow."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from continuum_core.corpus import (
    HIGH_AUTHORITY,
    ObservationRole,
    ObservationStatus,
    ProductionEvidenceRole,
    ProductionModelStatus,
)
from continuum_db.models import (
    CharacterObservation,
    CharacterOutfit,
    CharacterProductionEvidence,
    CharacterProductionModel,
    CharacterProfile,
    ReferenceItem,
)
from continuum_library import CatalogConflictError, CatalogInputError, CatalogNotFoundError
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def model_view(
    model: CharacterProductionModel, evidence: Sequence[CharacterProductionEvidence]
) -> dict[str, Any]:
    return {
        "id": str(model.id),
        "project_key": model.project_key,
        "character_id": str(model.character_id),
        "version": model.version,
        "status": model.status,
        "name": model.name,
        "summary": model.summary,
        "identity_rules": list(model.identity_rules or []),
        "restrictions": list(model.restrictions or []),
        "active_outfit_id": str(model.active_outfit_id) if model.active_outfit_id else None,
        "head_sheet_reference_id": str(model.head_sheet_reference_id)
        if model.head_sheet_reference_id
        else None,
        "body_sheet_reference_id": str(model.body_sheet_reference_id)
        if model.body_sheet_reference_id
        else None,
        "created_from": dict(model.created_from or {}),
        "approved_at": model.approved_at.isoformat() if model.approved_at else None,
        "approved_by": model.approved_by,
        "row_version": model.row_version,
        "evidence": [
            {
                "id": str(link.id),
                "observation_id": str(link.observation_id),
                "role": link.role,
                "preferred": link.preferred,
                "required": link.required,
                "position": link.position,
                "notes": link.notes,
            }
            for link in sorted(evidence, key=lambda item: (item.position, str(item.id)))
        ],
    }


class CharacterModels:
    def __init__(self, session: Session):
        self.session = session

    def _model(self, model_id: uuid.UUID) -> CharacterProductionModel:
        model = self.session.get(CharacterProductionModel, model_id)
        if model is None:
            raise CatalogNotFoundError("That character production model does not exist.")
        return model

    def evidence(self, model_id: uuid.UUID) -> list[CharacterProductionEvidence]:
        return list(
            self.session.execute(
                select(CharacterProductionEvidence)
                .where(CharacterProductionEvidence.model_id == model_id)
                .order_by(CharacterProductionEvidence.position, CharacterProductionEvidence.id)
            ).scalars()
        )

    def view(self, model: CharacterProductionModel) -> dict[str, Any]:
        return model_view(model, self.evidence(model.id))

    def list(self, project_key: str | None, character_id: uuid.UUID) -> list[dict[str, Any]]:
        query = select(CharacterProductionModel).where(
            CharacterProductionModel.character_id == character_id
        )
        if project_key is not None:
            query = query.where(CharacterProductionModel.project_key == project_key)
        rows = self.session.execute(
            query.order_by(
                CharacterProductionModel.updated_at.desc(), CharacterProductionModel.version.desc()
            )
        ).scalars()
        return [self.view(row) for row in rows]

    def active(self, project_key: str, character_id: uuid.UUID) -> CharacterProductionModel | None:
        return self.session.execute(
            select(CharacterProductionModel)
            .where(
                CharacterProductionModel.project_key == project_key,
                CharacterProductionModel.character_id == character_id,
                CharacterProductionModel.status == ProductionModelStatus.APPROVED.value,
            )
            .order_by(CharacterProductionModel.version.desc())
            .limit(1)
        ).scalar_one_or_none()

    def bundle(self, project_key: str, character_id: uuid.UUID) -> dict[str, Any] | None:
        model = self.active(project_key, character_id)
        if model is None:
            return None
        links = self.evidence(model.id)
        observations = (
            {
                row.id: row
                for row in self.session.execute(
                    select(CharacterObservation).where(
                        CharacterObservation.id.in_([link.observation_id for link in links])
                    )
                ).scalars()
            }
            if links
            else {}
        )
        view = self.view(model)
        view["evidence"] = [
            {
                **item,
                "locator": observations[uuid.UUID(item["observation_id"])].locator,
                "reference_id": str(observations[uuid.UUID(item["observation_id"])].reference_id)
                if observations[uuid.UUID(item["observation_id"])].reference_id
                else None,
                "authority": observations[uuid.UUID(item["observation_id"])].authority,
                "status": observations[uuid.UUID(item["observation_id"])].status,
                "facets": observations[uuid.UUID(item["observation_id"])].facets,
            }
            for item in view["evidence"]
            if observations[uuid.UUID(item["observation_id"])].status
            == ObservationStatus.CONFIRMED.value
        ]
        return view

    def create(
        self,
        project_key: str,
        character_id: uuid.UUID,
        *,
        name: str,
        summary: str = "",
        identity_rules: Sequence[str] = (),
        restrictions: Sequence[str] = (),
        active_outfit_id: uuid.UUID | None = None,
        head_sheet_reference_id: uuid.UUID | None = None,
        body_sheet_reference_id: uuid.UUID | None = None,
        created_from: dict[str, Any] | None = None,
    ) -> CharacterProductionModel:
        if self.session.get(CharacterProfile, character_id) is None:
            raise CatalogNotFoundError("That character does not exist.")
        if active_outfit_id:
            outfit = self.session.get(CharacterOutfit, active_outfit_id)
            if outfit is None or outfit.character_id != character_id:
                raise CatalogInputError("The active outfit must belong to this character.")
        for ref_id in (head_sheet_reference_id, body_sheet_reference_id):
            if ref_id and self.session.get(ReferenceItem, ref_id) is None:
                raise CatalogInputError("A sheet reference does not exist.")
        version = (
            self.session.execute(
                select(func.max(CharacterProductionModel.version)).where(
                    CharacterProductionModel.project_key == project_key,
                    CharacterProductionModel.character_id == character_id,
                )
            ).scalar_one()
            or 0
        ) + 1
        model = CharacterProductionModel(
            project_key=project_key,
            character_id=character_id,
            version=version,
            status=ProductionModelStatus.DRAFT.value,
            name=name.strip(),
            summary=summary.strip(),
            identity_rules=[str(x).strip() for x in identity_rules if str(x).strip()],
            restrictions=[str(x).strip() for x in restrictions if str(x).strip()],
            active_outfit_id=active_outfit_id,
            head_sheet_reference_id=head_sheet_reference_id,
            body_sheet_reference_id=body_sheet_reference_id,
            created_from=created_from or {},
        )
        if not model.name:
            raise CatalogInputError("A production model needs a name.")
        self.session.add(model)
        self.session.flush()
        return model

    def add_evidence(
        self,
        model_id: uuid.UUID,
        observation_id: uuid.UUID,
        role: ProductionEvidenceRole,
        *,
        preferred: bool = False,
        required: bool = False,
        position: int = 0,
        notes: str = "",
    ) -> CharacterProductionEvidence:
        model = self._model(model_id)
        if model.status not in {
            ProductionModelStatus.DRAFT.value,
            ProductionModelStatus.REVIEW.value,
        }:
            raise CatalogConflictError("Approved or superseded production models are immutable.")
        observation = self.session.get(CharacterObservation, observation_id)
        if observation is None or observation.character_id != model.character_id:
            raise CatalogInputError("Evidence must be an observation of this character.")
        if observation.status != ObservationStatus.CONFIRMED.value:
            raise CatalogInputError(
                "Candidate or rejected observations cannot ground a production model."
            )
        grounding_roles = {
            ProductionEvidenceRole.IDENTITY,
            ProductionEvidenceRole.BODY,
            ProductionEvidenceRole.WARDROBE,
            ProductionEvidenceRole.ACCESSORY,
            ProductionEvidenceRole.SCALE,
        }
        if role in grounding_roles and (
            observation.role != ObservationRole.GROUNDING.value
            or observation.authority not in {x.value for x in HIGH_AUTHORITY}
        ):
            raise CatalogInputError(
                "Identity, body and wardrobe evidence must be confirmed high-authority grounding."
            )
        link = CharacterProductionEvidence(
            model_id=model.id,
            observation_id=observation.id,
            role=role.value,
            preferred=preferred,
            required=required,
            position=position,
            notes=notes.strip(),
        )
        self.session.add(link)
        self.session.flush()
        return link

    def submit(self, model_id: uuid.UUID) -> CharacterProductionModel:
        model = self._model(model_id)
        if model.status != ProductionModelStatus.DRAFT.value:
            raise CatalogConflictError("Only a draft can be submitted for review.")
        if not self.evidence(model.id):
            raise CatalogInputError("Add confirmed evidence before review.")
        model.status = ProductionModelStatus.REVIEW.value
        self.session.flush()
        return model

    def approve(self, model_id: uuid.UUID, reviewer: str) -> CharacterProductionModel:
        model = self._model(model_id)
        reviewer = reviewer.strip()
        if model.status != ProductionModelStatus.REVIEW.value:
            raise CatalogConflictError("Only a model in review can be approved.")
        if not reviewer:
            raise CatalogInputError("A human reviewer is required.")
        previous = self.active(model.project_key, model.character_id)
        if previous and previous.id != model.id:
            previous.status = ProductionModelStatus.SUPERSEDED.value
            previous.approved_at = None
            previous.approved_by = None
        model.status = ProductionModelStatus.APPROVED.value
        model.approved_at = _now()
        model.approved_by = reviewer
        self.session.flush()
        return model
