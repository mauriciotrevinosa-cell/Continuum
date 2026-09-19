"""Visual Knowledge retrieval: the narrowest evidence for one visual problem (M3).

A Visual Knowledge item is a catalog reference. Retrieval answers "which
references teach *this* problem?" from what people (or analyzers) recorded
about them - technique facets, descriptors and the project's standing - and
explains every choice.

Rules:

* only **sorted** references are retrieved (``UNSORTED`` means nobody decided
  what the material is for);
* a reference linked to a character is **never** retrieved here: identity and
  wardrobe come from the character corpus, and a character's evidence never
  becomes a style or technique reference by accident;
* technique rows tied to a visual mode (a scene treatment) only count when that
  treatment is asked for;
* material from an external resource whose allowed uses exclude ``RETRIEVAL``
  is never retrieved, however well it matches;
* analyzer descriptors below 0.5 confidence do not count.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from typing import Any

from continuum_core.catalog import RightsStatus, TrainingEligibility
from continuum_core.knowledge import KnowledgeUse
from continuum_core.references import (
    DescriptorOrigin,
    ProjectStanding,
    ReferenceClass,
    TechniqueFacet,
)
from continuum_db.models import (
    CatalogEntry,
    ExternalResource,
    ProjectReferenceStanding,
    ReferenceCharacter,
    ReferenceDescriptor,
    ReferenceItem,
    ReferenceTechnique,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

__all__ = ["VisualKnowledge"]

_FACET_SCORE = 3.0
_TERM_SCORE = 2.0
_STANDING_SCORE = {
    ProjectStanding.PREFERRED_FOR_CURRENT_LOOK: 2.0,
    ProjectStanding.CANONICAL_FOR_PROJECT: 1.5,
    ProjectStanding.USEFUL: 1.0,
}
_MIN_ANALYSIS_CONFIDENCE = 0.5


class VisualKnowledge:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- retrieval ------------------------------------------------------------
    def retrieve(
        self,
        project_key: str,
        *,
        facets: Sequence[TechniqueFacet],
        terms: Sequence[str] = (),
        visual_mode_ids: Collection[uuid.UUID] = (),
        limit: int = 4,
        exclude: Collection[uuid.UUID] = (),
    ) -> list[dict[str, Any]]:
        """References that teach one of ``facets`` or match one of ``terms``, best first."""
        wanted_terms = {t.strip().lower() for t in terms if t and t.strip()}
        matched_facets: dict[uuid.UUID, set[str]] = defaultdict(set)
        if facets:
            for reference_id, facet, mode in self.session.execute(
                select(
                    ReferenceTechnique.reference_id,
                    ReferenceTechnique.facet,
                    ReferenceTechnique.visual_mode_id,
                ).where(ReferenceTechnique.facet.in_(list(facets)))
            ).all():
                if mode is None or mode in visual_mode_ids:
                    matched_facets[reference_id].add(facet.value)
        matched_terms: dict[uuid.UUID, set[str]] = defaultdict(set)
        if wanted_terms:
            for reference_id, facet, value, origin, confidence in self.session.execute(
                select(
                    ReferenceDescriptor.reference_id,
                    ReferenceDescriptor.facet,
                    ReferenceDescriptor.value,
                    ReferenceDescriptor.origin,
                    ReferenceDescriptor.confidence,
                ).where(func.lower(ReferenceDescriptor.value).in_(wanted_terms))
            ).all():
                if (
                    origin is DescriptorOrigin.ANALYSIS
                    and confidence is not None
                    and confidence < _MIN_ANALYSIS_CONFIDENCE
                ):
                    continue
                matched_terms[reference_id].add(f"{facet.value.lower()}: {value}")
        ids = (set(matched_facets) | set(matched_terms)) - set(exclude)
        return self._rank(project_key, ids, matched_facets, matched_terms, limit)

    def house_style(self, project_key: str, *, limit: int = 2) -> list[dict[str, Any]]:
        """The project's current-look exemplars: references a person marked preferred."""
        ids = set(
            self.session.execute(
                select(ProjectReferenceStanding.reference_id).where(
                    ProjectReferenceStanding.project_key == project_key,
                    ProjectReferenceStanding.standing == ProjectStanding.PREFERRED_FOR_CURRENT_LOOK,
                    ProjectReferenceStanding.character_id.is_(None),
                )
            ).scalars()
        )
        return self._rank(project_key, ids, {}, {}, limit)

    # -- internals ------------------------------------------------------------
    def _rank(
        self,
        project_key: str,
        ids: set[uuid.UUID],
        matched_facets: dict[uuid.UUID, set[str]],
        matched_terms: dict[uuid.UUID, set[str]],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        bound = set(
            self.session.execute(
                select(ReferenceCharacter.reference_id).where(
                    ReferenceCharacter.reference_id.in_(ids)
                )
            ).scalars()
        )
        items = list(
            self.session.execute(
                select(ReferenceItem).where(
                    ReferenceItem.id.in_(ids - bound),
                    ReferenceItem.removed_at.is_(None),
                    ReferenceItem.reference_class != ReferenceClass.UNSORTED,
                )
            ).scalars()
        )
        blocked = self._without_retrieval(items)
        standings: dict[uuid.UUID, ProjectStanding] = {}
        for reference_id, standing in self.session.execute(
            select(ProjectReferenceStanding.reference_id, ProjectReferenceStanding.standing).where(
                ProjectReferenceStanding.project_key == project_key,
                ProjectReferenceStanding.reference_id.in_([item.id for item in items]),
                ProjectReferenceStanding.character_id.is_(None),
            )
        ).all():
            current = standings.get(reference_id)
            if current is None or _STANDING_SCORE[standing] > _STANDING_SCORE[current]:
                standings[reference_id] = standing
        ranked: list[dict[str, Any]] = []
        for item in items:
            if item.id in blocked:
                continue
            facet_hits = sorted(matched_facets.get(item.id, ()))
            term_hits = sorted(matched_terms.get(item.id, ()))
            standing = standings.get(item.id)
            score = (
                _FACET_SCORE * len(facet_hits)
                + _TERM_SCORE * len(term_hits)
                + (_STANDING_SCORE[standing] if standing else 0.0)
            )
            why = [f"teaches {facet.lower().replace('_', ' ')}" for facet in facet_hits]
            why += [f"described as {term}" for term in term_hits]
            if standing is ProjectStanding.PREFERRED_FOR_CURRENT_LOOK:
                why.append("preferred for the project's current look (house style)")
            elif standing is not None:
                why.append(f"project standing: {standing.value.lower().replace('_', ' ')}")
            warnings = []
            if item.rights_status is RightsStatus.UNKNOWN:
                warnings.append("rights unknown")
            if item.training_eligibility is not TrainingEligibility.APPROVED:
                warnings.append("not approved for training")
            ranked.append(
                {
                    "reference_id": str(item.id),
                    "locator": item.locator,
                    "label": item.label,
                    "reference_class": item.reference_class.value,
                    "origin": item.origin.value,
                    "matched_facets": facet_hits,
                    "matched_descriptors": term_hits,
                    "standing": standing.value if standing else None,
                    "score": round(score, 2),
                    "why": why,
                    "rights_status": item.rights_status.value,
                    "training_eligibility": item.training_eligibility.value,
                    "warnings": warnings,
                    "identity_evidence": False,
                    "_created": item.created_at,
                }
            )
        ranked.sort(key=lambda entry: (-entry["score"], entry["_created"], entry["reference_id"]))
        for entry in ranked:
            entry.pop("_created")
        return ranked[:limit]

    def _without_retrieval(self, items: Sequence[ReferenceItem]) -> set[uuid.UUID]:
        """Items imported from an intake root bound to a resource that forbids retrieval."""
        blocked_roots = {
            row.intake_root_key
            for row in self.session.execute(
                select(ExternalResource).where(ExternalResource.intake_root_key.is_not(None))
            ).scalars()
            if KnowledgeUse.RETRIEVAL.value not in row.allowed_uses
        }
        if not blocked_roots:
            return set()
        entry_of = {
            item.id: str((item.provenance or {}).get("catalog_entry_id") or "")
            for item in items
            if (item.provenance or {}).get("catalog_entry_id")
        }
        if not entry_of:
            return set()
        wanted = []
        for value in entry_of.values():
            try:
                wanted.append(uuid.UUID(value))
            except ValueError:
                continue
        roots = {
            str(entry_id): root
            for entry_id, root in self.session.execute(
                select(CatalogEntry.id, CatalogEntry.root_key).where(CatalogEntry.id.in_(wanted))
            ).all()
        }
        return {item_id for item_id, entry in entry_of.items() if roots.get(entry) in blocked_roots}
