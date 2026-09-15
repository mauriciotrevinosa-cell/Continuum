"""Timeline-aware project wardrobe (M3 W6).

Clothing is a layer on top of identity, never identity itself. This module
adds the two behaviours the approved Wardrobe v1 direction requires:

* a **project-created outfit** has a human review state and an optional model
  sheet, and never self-approves;
* a garment has an **owner** (``character_outfit.character_id``) and may be
  **worn by a different character** in a specific project/story stage via
  ``outfit_wear``. Borrowing is append-only: a later assignment never rewrites
  an earlier one, so Frieren wearing Mau's hoodie in E14/E18 never makes that
  hoodie Frieren's default E1-E13 outfit, and never clones Mau's identity.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core.references import OutfitKind, OutfitReviewStatus
from continuum_db.models import CharacterOutfit, CharacterProfile, OutfitWear
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

    def assign_wear(
        self,
        outfit_id: uuid.UUID,
        wearer_character_id: uuid.UUID,
        project_key: str,
        stage: str,
        *,
        context: str = "",
        notes: str = "",
    ) -> OutfitWear:
        """Record who wears a garment in one project/story stage.

        Deterministic upsert keyed by (outfit, project, stage): re-recording
        the same input is a no-op, and a conflicting wearer for the same stage
        is refused rather than silently rewriting earlier continuity.
        """
        self.outfit(outfit_id)
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
            notes=notes.strip(),
        )
        self.session.add(row)
        self.session.flush()
        return row

    def resolve(
        self, project_key: str, character_id: uuid.UUID, stage: str
    ) -> dict[str, Any] | None:
        """The outfit a character wears at a story stage, owner vs wearer kept apart.

        An explicit ``outfit_wear`` assignment wins; otherwise the character's
        own project outfit is returned. The result always names the owner and
        the wearer separately, and flags a borrowed garment.
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
        ).first()
        if found is not None:
            wear, outfit = found
            return self._resolved(outfit, character_id, wear)
        outfit = self.session.execute(
            select(CharacterOutfit)
            .where(
                CharacterOutfit.character_id == character_id,
                CharacterOutfit.project_key == project_key,
                CharacterOutfit.removed_at.is_(None),
            )
            .order_by(CharacterOutfit.created_at, CharacterOutfit.id)
        ).scalars().first()
        if outfit is not None:
            return self._resolved(outfit, character_id, None)
        return None

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
            "condition": outfit.condition,
            "review_status": outfit.review_status,
            "model_sheet_reference_id": str(outfit.model_sheet_reference_id)
            if outfit.model_sheet_reference_id
            else None,
            "stage": wear.stage if wear else None,
            "context": wear.context if wear else None,
        }
