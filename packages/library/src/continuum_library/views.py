"""Read models for the Character Vault, the Style Vault, references and the inbox.

Plain dictionaries, assembled in one place so every surface shows the same
facts the same way: identity, wardrobe and acting apart; user tags labelled
USER TAGGED and analyzer output ANALYSIS DERIVED; origin always visible.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from continuum_core.references import (
    ASPECT_GROUPS,
    AspectGroup,
    CharacterAspect,
    DescriptorOrigin,
)
from continuum_db.models import (
    CharacterOutfit,
    CharacterProfile,
    LibraryAsset,
    ProjectPanelSource,
    ProjectReferenceStanding,
    ProjectVisualModeAssignment,
    ReferenceCandidate,
    ReferenceCharacter,
    ReferenceDescriptor,
    ReferenceItem,
    ReferenceTechnique,
    ReferenceUseLink,
    VisualMode,
)
from sqlalchemy import select

from continuum_library.catalog import ReferenceCatalog, region_of

__all__ = [
    "candidate_view",
    "character_summary",
    "character_vault",
    "reference_view",
    "style_vault",
    "visual_mode_view",
]

DESCRIPTOR_LABEL = {
    DescriptorOrigin.USER: "USER TAGGED",
    DescriptorOrigin.ANALYSIS: "ANALYSIS DERIVED",
}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def character_summary(character: CharacterProfile) -> dict[str, Any]:
    return {
        "id": str(character.id),
        "display_name": character.display_name,
        "subject_kind": character.subject_kind.value,
        "source_label": character.source_label,
        "summary": character.summary,
        "scale_notes": character.scale_notes,
        "distinguishing_marks": character.distinguishing_marks,
        "posture_notes": character.posture_notes,
        "notes": character.notes,
        "row_version": character.row_version,
        "updated_at": _iso(character.updated_at),
    }


def _outfit(outfit: CharacterOutfit) -> dict[str, Any]:
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
        "row_version": outfit.row_version,
    }


def visual_mode_view(mode: VisualMode) -> dict[str, Any]:
    return {
        "id": str(mode.id),
        "name": mode.name,
        "category": mode.category.value,
        "description": mode.description,
        "notes": mode.notes,
        "row_version": mode.row_version,
    }


def reference_view(
    catalog: ReferenceCatalog, item: ReferenceItem, *, with_source: bool = True
) -> dict[str, Any]:
    session = catalog.session
    asset = session.get(LibraryAsset, item.asset_id)
    characters = session.execute(
        select(ReferenceCharacter, CharacterProfile, CharacterOutfit)
        .join(CharacterProfile, CharacterProfile.id == ReferenceCharacter.character_id)
        .outerjoin(CharacterOutfit, CharacterOutfit.id == ReferenceCharacter.outfit_id)
        .where(ReferenceCharacter.reference_id == item.id)
        .order_by(ReferenceCharacter.created_at, ReferenceCharacter.id)
    ).all()
    techniques = session.execute(
        select(ReferenceTechnique, VisualMode)
        .outerjoin(VisualMode, VisualMode.id == ReferenceTechnique.visual_mode_id)
        .where(ReferenceTechnique.reference_id == item.id)
        .order_by(ReferenceTechnique.created_at, ReferenceTechnique.id)
    ).all()
    descriptors = session.execute(
        select(ReferenceDescriptor)
        .where(ReferenceDescriptor.reference_id == item.id)
        .order_by(ReferenceDescriptor.facet, ReferenceDescriptor.value)
    ).scalars()
    standings = session.execute(
        select(ProjectReferenceStanding).where(ProjectReferenceStanding.reference_id == item.id)
    ).scalars()
    panel_sources = session.execute(
        select(ProjectPanelSource).where(ProjectPanelSource.reference_id == item.id)
    ).scalars()
    uses = session.execute(
        select(ReferenceUseLink).where(ReferenceUseLink.reference_id == item.id)
    ).scalars()
    region = region_of(item)
    view: dict[str, Any] = {
        "id": str(item.id),
        "locator": item.locator,
        "unit_index": item.unit_index,
        "region": region.as_dict() if region else None,
        "reference_class": item.reference_class.value,
        "origin": item.origin.value,
        "label": item.label,
        "notes": item.notes,
        "source_url": item.source_url,
        "creator_handle": item.creator_handle,
        "favorite": item.favorite,
        "provenance": item.provenance,
        "medium": asset.medium.value if asset else None,
        "asset_origin": asset.origin.value if asset else None,
        "row_version": item.row_version,
        "created_at": _iso(item.created_at),
        "removed": item.removed_at is not None,
        "previewable": not item.locator.startswith("pdf:"),
        "uses": [u.use.value for u in uses],
        "characters": [
            {
                "link_id": str(link.id),
                "character_id": str(character.id),
                "character_name": character.display_name,
                "aspect": link.aspect.value,
                "group": ASPECT_GROUPS[link.aspect].value,
                "outfit_id": str(outfit.id) if outfit else None,
                "outfit_name": outfit.name if outfit else None,
                "preferred": link.preferred,
                "notes": link.notes,
            }
            for link, character, outfit in characters
        ],
        "techniques": [
            {
                "link_id": str(link.id),
                "facet": link.facet.value,
                "visual_mode_id": str(mode.id) if mode else None,
                "visual_mode_name": mode.name if mode else None,
                "notes": link.notes,
            }
            for link, mode in techniques
        ],
        "descriptors": [
            {
                "id": str(d.id),
                "facet": d.facet.value,
                "value": d.value,
                "origin": d.origin.value,
                "origin_label": DESCRIPTOR_LABEL[d.origin],
                "confidence": d.confidence,
                "analyzer_ref": d.analyzer_ref,
            }
            for d in descriptors
        ],
        "standings": [
            {
                "id": str(s.id),
                "project_key": s.project_key,
                "standing": s.standing.value,
                "character_id": str(s.character_id) if s.character_id else None,
                "notes": s.notes,
            }
            for s in standings
        ],
        "panel_sources": [
            {
                "id": str(p.id),
                "project_key": p.project_key,
                "episode": p.episode,
                "chapter": p.chapter,
                "page": p.page,
                "panel": p.panel,
                "role": p.role.value,
                "notes": p.notes,
            }
            for p in panel_sources
        ],
    }
    if with_source:
        view["source"] = catalog.source_position(item)
    return view


def character_vault(catalog: ReferenceCatalog, character_id: uuid.UUID) -> dict[str, Any]:
    """A character's references, organized for production use."""
    character = catalog.character(character_id)
    outfits = catalog.outfits(character_id)
    rows = catalog.session.execute(
        select(ReferenceCharacter, ReferenceItem)
        .join(ReferenceItem, ReferenceItem.id == ReferenceCharacter.reference_id)
        .where(
            ReferenceCharacter.character_id == character_id,
            ReferenceItem.removed_at.is_(None),
        )
        .order_by(
            ReferenceCharacter.preferred.desc(),
            ReferenceItem.created_at.desc(),
            ReferenceItem.id.desc(),
        )
    ).all()
    views: dict[uuid.UUID, dict[str, Any]] = {}
    groups: dict[AspectGroup, dict[CharacterAspect, list[dict[str, Any]]]] = {
        group: defaultdict(list) for group in AspectGroup
    }
    by_outfit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_origin: dict[str, int] = defaultdict(int)
    preferred: list[dict[str, Any]] = []
    for link, item in rows:
        if item.id not in views:
            views[item.id] = reference_view(catalog, item, with_source=False)
            by_origin[item.origin.value] += 1
        card = {
            "reference": views[item.id],
            "link_id": str(link.id),
            "aspect": link.aspect.value,
            "preferred": link.preferred,
            "outfit_id": str(link.outfit_id) if link.outfit_id else None,
            "notes": link.notes,
        }
        groups[ASPECT_GROUPS[link.aspect]][link.aspect].append(card)
        if link.outfit_id is not None:
            by_outfit[str(link.outfit_id)].append(card)
        if link.preferred:
            preferred.append(card)
    standings = catalog.session.execute(
        select(ProjectReferenceStanding).where(
            ProjectReferenceStanding.reference_id.in_(list(views)),
        )
    ).scalars()
    project: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for standing in standings:
        if standing.character_id in (None, character_id):
            project[standing.project_key][standing.standing.value].append(
                str(standing.reference_id)
            )
    assignments = catalog.session.execute(
        select(ProjectVisualModeAssignment, VisualMode)
        .join(VisualMode, VisualMode.id == ProjectVisualModeAssignment.visual_mode_id)
        .where(ProjectVisualModeAssignment.character_id == character_id)
    ).all()
    return {
        "character": character_summary(character),
        "identity": {aspect.value: cards for aspect, cards in groups[AspectGroup.IDENTITY].items()},
        "acting": {aspect.value: cards for aspect, cards in groups[AspectGroup.ACTING].items()},
        "wardrobe": {
            "outfits": [
                {**_outfit(o), "references": by_outfit.get(str(o.id), [])} for o in outfits
            ],
            "unassigned": [
                card
                for aspect_cards in groups[AspectGroup.WARDROBE].values()
                for card in aspect_cards
                if card["outfit_id"] is None
            ],
        },
        "preferred": preferred,
        "sources": dict(by_origin),
        "project_standing": {key: dict(value) for key, value in project.items()},
        "scoped_visual_modes": [
            {
                "assignment_id": str(a.id),
                "project_key": a.project_key,
                "visual_mode": visual_mode_view(mode),
                "scope": a.scope.value,
                "trigger": a.trigger.value,
                "episode": a.episode,
                "event_label": a.event_label,
            }
            for a, mode in assignments
        ],
        "reference_count": len(views),
    }


def style_vault(catalog: ReferenceCatalog) -> dict[str, Any]:
    """Visual modes and technique references, by mode and by facet."""
    modes = catalog.list_visual_modes()
    rows = catalog.session.execute(
        select(ReferenceTechnique, ReferenceItem)
        .join(ReferenceItem, ReferenceItem.id == ReferenceTechnique.reference_id)
        .where(ReferenceItem.removed_at.is_(None))
        .order_by(ReferenceItem.created_at.desc(), ReferenceItem.id.desc())
    ).all()
    views: dict[uuid.UUID, dict[str, Any]] = {}
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_facet: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link, item in rows:
        if item.id not in views:
            views[item.id] = reference_view(catalog, item, with_source=False)
        card = {"reference": views[item.id], "facet": link.facet.value, "notes": link.notes}
        by_facet[link.facet.value].append(card)
        if link.visual_mode_id is not None:
            by_mode[str(link.visual_mode_id)].append(card)
    return {
        "modes": [{**visual_mode_view(m), "references": by_mode.get(str(m.id), [])} for m in modes],
        "by_facet": dict(by_facet),
        "reference_count": len(views),
    }


def candidate_view(candidate: ReferenceCandidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "batch_id": str(candidate.batch_id) if candidate.batch_id else None,
        "intake_kind": candidate.intake_kind.value,
        "status": candidate.status.value,
        "source_url": candidate.source_url,
        "creator_handle": candidate.creator_handle,
        "display_name": candidate.display_name,
        "has_file": candidate.asset_id is not None,
        "capture": candidate.capture,
        "origin": candidate.origin.value,
        "suggested_class": candidate.suggested_class.value if candidate.suggested_class else None,
        "intended_uses": list(candidate.intended_uses),
        "tags": list(candidate.tags),
        "notes": candidate.notes,
        "reference_id": str(candidate.reference_id) if candidate.reference_id else None,
        "row_version": candidate.row_version,
        "created_at": _iso(candidate.created_at),
    }
