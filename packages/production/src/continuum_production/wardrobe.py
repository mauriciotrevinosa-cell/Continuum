"""Timeline-aware project wardrobe (M3 W6).

Clothing is a layer on top of identity, never identity itself. This module
adds the behaviours the approved Wardrobe v1 direction requires:

* a **project-created outfit** has a human review state and an optional model
  sheet, and never self-approves;
* a garment has an **owner** (``character_outfit.character_id``) and may be
  **worn by a different character** in a specific project/story stage via
  ``outfit_wear``. Borrowing is append-only: a later assignment never rewrites
  an earlier one, so Frieren wearing Mau's hoodie in E14/E18 never makes that
  hoodie Frieren's default E1-E13 outfit, and never clones Mau's identity;
* a character may wear **several garments at once** in a stage (a hoodie, a
  cap and their own bottoms), so resolution returns a set, not one arbitrary
  outfit;
* a garment's **condition is stage-scoped** on the wear assignment, so
  clean -> dirty -> damaged -> repaired can be represented without rewriting
  the garment's identity or earlier continuity;
* only an **APPROVED** project-created outfit resolves into production
  wardrobe. Source/default outfits are not gated by review.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core.references import OutfitKind, OutfitReviewStatus
from continuum_db.models import CharacterOutfit, CharacterProfile, OutfitWear, ReferenceItem
from continuum_library import CatalogConflictError, CatalogInputError, CatalogNotFoundError
from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = ["Wardrobe", "outfit_view", "wear_view"]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def outfit_view(outfit: CharacterOutfit) -> dict[str, Any]:
    return {
        "id": str(outfit.id),
        "character_id": str(outfit.character_id),
        "name": outfit.name,
        "kind": outfit.kind.value,
        "project_key": outfit.project_key,
        "era": outfit.era,
        "season_weather": outfit.season_weather,
        "condition": outfit.condition,
        "notes": outfit.notes,
        "review_status": outfit.review_status,
        "reviewed_by": outfit.reviewed_by,
        "model_sheet_reference_id": str(outfit.model_sheet_reference_id)
        if outfit.model_sheet_reference_id
        else None,
        "row_version": outfit.row_version,
    }


def wear_view(wear: OutfitWear) -> dict[str, Any]:
    return {
        "id": str(wear.id),
        "outfit_id": str(wear.outfit_id),
        "wearer_character_id": str(wear.wearer_character_id),
        "project_key": wear.project_key,
        "stage": wear.stage,
        "context": wear.context,
        "condition": wear.condition,
        "notes": wear.notes,
    }


class Wardrobe:
    def __init__(self, session: Session):
        self.session = session

    def outfit(self, outfit_id: uuid.UUID) -> CharacterOutfit:
        row = self.session.get(CharacterOutfit, outfit_id)
        if row is None or row.removed_at is not None:
            raise CatalogNotFoundError("That outfit does not exist.")
        return row

    def review(
        self, outfit_id: uuid.UUID, decision: str, reviewer: str, notes: str = ""
    ) -> CharacterOutfit:
        """A person reviews a project-created outfit. Source outfits are not reviewed."""
        row = self.outfit(outfit_id)
        if row.kind is not OutfitKind.PROJECT:
            raise CatalogConflictError("Only a project-created outfit is reviewed.")
        reviewer = reviewer.strip()
        if not reviewer:
            raise CatalogInputError("A human reviewer is required.")
        try:
            status = OutfitReviewStatus(decision)
        except ValueError:
            raise CatalogInputError(
                "Decision must be DRAFT, REVIEW, APPROVED or REJECTED."
            ) from None
        row.review_status = status.value
        row.reviewed_by = reviewer
        row.reviewed_at = _now()
        if notes.strip():
            row.notes = (row.notes + "\n" + notes.strip()).strip()
        self.session.flush()
        return row

    def attach_model_sheet(self, outfit_id: uuid.UUID, reference_id: uuid.UUID) -> CharacterOutfit:
        """Attach or replace an outfit's model-sheet / turnaround reference.

        The reference must exist and not be removed. This is the human-controlled
        path that populates ``character_outfit.model_sheet_reference_id``.
        """
        outfit = self.outfit(outfit_id)
        reference = self.session.get(ReferenceItem, reference_id)
        if reference is None or reference.removed_at is not None:
            raise CatalogNotFoundError("That reference does not exist.")
        outfit.model_sheet_reference_id = reference_id
        self.session.flush()
        return outfit

    def assign_wear(
        self,
        outfit_id: uuid.UUID,
        wearer_character_id: uuid.UUID,
        project_key: str,
        stage: str,
        *,
        context: str = "",
        condition: str = "",
        notes: str = "",
    ) -> OutfitWear:
        """Record who wears a garment in one project/story stage.

        Deterministic upsert keyed by (outfit, project, stage): re-recording
        the same input is a no-op, and a conflicting wearer for the same stage
        is refused rather than silently rewriting earlier continuity.

        A PROJECT outfit may only be worn in its own project; cross-project
        assignment is refused rather than silently accepted.
        """
        outfit = self.outfit(outfit_id)
        if outfit.kind is OutfitKind.PROJECT and outfit.project_key != project_key:
            raise CatalogConflictError("A project outfit can only be worn in its own project.")
        wearer = self.session.get(CharacterProfile, wearer_character_id)
        if wearer is None or wearer.removed_at is not None:
            raise CatalogNotFoundError("That wearer does not exist.")
        stage = stage.strip()
        if not stage:
            raise CatalogInputError("A story stage is required.")
        existing = self.session.execute(
            select(OutfitWear).where(
                OutfitWear.outfit_id == outfit_id,
                OutfitWear.project_key == project_key,
                OutfitWear.stage == stage,
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.wearer_character_id != wearer_character_id:
                raise CatalogConflictError(
                    "That outfit is already assigned to a different wearer for this stage."
                )
            return existing
        row = OutfitWear(
            outfit_id=outfit_id,
            wearer_character_id=wearer_character_id,
            project_key=project_key,
            stage=stage,
            context=context.strip()[:200],
            condition=condition.strip()[:120],
            notes=notes.strip(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def resolve(
        self, project_key: str, character_id: uuid.UUID, stage: str
    ) -> list[dict[str, Any]]:
        """The set of garments a character wears at a story stage.

        Returns a list (possibly empty), because a character may wear several
        garments at once. Explicit ``outfit_wear`` assignments win; otherwise
        the character's own project outfit is returned. The result always names
        the owner and the wearer separately, and flags a borrowed garment.

        A PROJECT outfit that is not APPROVED never resolves into production
        wardrobe. Source/default outfits are not gated by review.
        """
        found = self.session.execute(
            select(OutfitWear, CharacterOutfit)
            .join(CharacterOutfit, CharacterOutfit.id == OutfitWear.outfit_id)
            .where(
                OutfitWear.wearer_character_id == character_id,
                OutfitWear.project_key == project_key,
                OutfitWear.stage == stage,
                CharacterOutfit.removed_at.is_(None),
            )
            .order_by(OutfitWear.created_at, OutfitWear.id)
        ).all()
        if found:
            return [
                self._resolved(outfit, character_id, wear)
                for wear, outfit in found
                if self._production_ready(outfit)
            ]
        outfit = (
            self.session.execute(
                select(CharacterOutfit)
                .where(
                    CharacterOutfit.character_id == character_id,
                    CharacterOutfit.project_key == project_key,
                    CharacterOutfit.removed_at.is_(None),
                )
                .order_by(CharacterOutfit.created_at, CharacterOutfit.id)
            )
            .scalars()
            .first()
        )
        if outfit is not None and self._production_ready(outfit):
            return [self._resolved(outfit, character_id, None)]
        return []

    def _production_ready(self, outfit: CharacterOutfit) -> bool:
        """A source/default outfit is always ready; a PROJECT outfit must be APPROVED."""
        if outfit.kind is not OutfitKind.PROJECT:
            return True
        return outfit.review_status == OutfitReviewStatus.APPROVED.value

    def _resolved(
        self, outfit: CharacterOutfit, wearer_id: uuid.UUID, wear: OutfitWear | None
    ) -> dict[str, Any]:
        return {
            "outfit_id": str(outfit.id),
            "name": outfit.name,
            "kind": outfit.kind.value,
            "owner_character_id": str(outfit.character_id),
            "wearer_character_id": str(wearer_id),
            "borrowed": outfit.character_id != wearer_id,
            "project_key": outfit.project_key,
            "era": outfit.era,
            "season_weather": outfit.season_weather,
            "condition": wear.condition if wear else outfit.condition,
            "review_status": outfit.review_status,
            "model_sheet_reference_id": str(outfit.model_sheet_reference_id)
            if outfit.model_sheet_reference_id
            else None,
            "stage": wear.stage if wear else None,
            "context": wear.context if wear else None,
        }
