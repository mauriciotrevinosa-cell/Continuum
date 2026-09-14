"""Character manifests: every reference that can ground a character, by what it grounds.

A single preferred picture is not a character definition. Production needs a
complementary set - a face, the body and proportions, the wardrobe, acting,
poses, accessories - drawn from the canonical manga, the anime, approved
supplemental material and the project's own work. This module resolves that
set from the Reference Vault for one character and one project:

* **facets** group references by what they ground (identity, body, wardrobe,
  expression, pose, accessories);
* **lanes** say where each reference comes from (canonical manga, anime
  frame, official art, supplemental fan art, project-created);
* **preferred** only ranks references inside a facet; it never hides the rest;
* **fan art** grounds a character only when the project has explicitly given
  that reference a standing; otherwise it is listed as not selected;
* **unsorted** material never grounds anything;
* an **original project character** is never grounded in franchise material:
  source pages, anime frames, official art and fan art cannot define their
  identity or body. Their design documents come from the project (a visual
  bible read from the project's committed documents), and a facet with no
  project reference is reported missing - nothing is substituted.

Every selected reference carries its full provenance. Resolution only reads.
"""

from __future__ import annotations

import uuid
from typing import Any

from continuum_core.references import (
    CharacterAspect,
    CharacterOrigin,
    ProjectStanding,
    ReferenceClass,
    ReferenceOrigin,
    ReferenceUse,
)
from continuum_db.models import (
    CharacterProfile,
    ProjectReferenceStanding,
    ReferenceCharacter,
    ReferenceItem,
    ReferenceUseLink,
)
from continuum_library import CatalogNotFoundError, ReferenceCatalog
from continuum_storage import ProjectLibrary
from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = [
    "FACETS",
    "LANES",
    "REQUIRED_FACETS",
    "character_manifest",
    "facet_of",
    "lane_of",
]

#: What a reference grounds, in production terms, and the aspects that belong to it.
FACETS: dict[str, tuple[CharacterAspect, ...]] = {
    "identity": (
        CharacterAspect.FACE,
        CharacterAspect.HAIR,
        CharacterAspect.DISTINGUISHING_MARK,
    ),
    "body": (
        CharacterAspect.FULL_BODY,
        CharacterAspect.PROPORTIONS,
        CharacterAspect.SCALE,
        CharacterAspect.POSTURE,
    ),
    "wardrobe": (CharacterAspect.OUTFIT,),
    "expression": (
        CharacterAspect.EXPRESSION,
        CharacterAspect.QUIET_ACTING,
        CharacterAspect.COMEDIC_EXPRESSION,
        CharacterAspect.GESTURE,
    ),
    "pose": (CharacterAspect.POSE, CharacterAspect.ACTION_POSE),
    "accessories": (CharacterAspect.ACCESSORY,),
}
#: Without these a character cannot be drawn consistently at all.
REQUIRED_FACETS: tuple[str, ...] = ("identity", "body")
LANES: tuple[str, ...] = (
    "canonical_manga",
    "anime",
    "official_art",
    "supplemental",
    "project_created",
)
_FRANCHISE_ORIGINS = frozenset(
    {ReferenceOrigin.SOURCE, ReferenceOrigin.OFFICIAL_ART, ReferenceOrigin.FAN_ART}
)
_STANDING_RANK = {
    ProjectStanding.CANONICAL_FOR_PROJECT: 0,
    ProjectStanding.PREFERRED_FOR_CURRENT_LOOK: 1,
    ProjectStanding.USEFUL: 2,
}


def facet_of(aspect: CharacterAspect) -> str:
    return next(name for name, aspects in FACETS.items() if aspect in aspects)


def lane_of(item: ReferenceItem) -> str:
    """Where a reference comes from, as a production lane."""
    if item.origin is ReferenceOrigin.FAN_ART:
        return "supplemental"
    if item.origin is ReferenceOrigin.OFFICIAL_ART:
        return "official_art"
    if item.origin in (
        ReferenceOrigin.USER_CREATED,
        ReferenceOrigin.GENERATED,
        ReferenceOrigin.PROJECT_APPROVED,
    ):
        return "project_created"
    kind = str((item.provenance or {}).get("kind") or "")
    if "frame" in kind or "&t=" in item.locator or "#t=" in item.locator:
        return "anime"
    return "canonical_manga"


def character_manifest(
    session: Session,
    catalog: ReferenceCatalog,
    character_id: uuid.UUID,
    *,
    project_key: str,
    projects: ProjectLibrary | None = None,
) -> dict[str, Any]:
    """The complementary reference set that grounds one character in one project."""
    from continuum_production.manifest import ReferenceManifests  # provenance shape, shared

    character = session.get(CharacterProfile, character_id)
    if character is None or character.removed_at is not None:
        raise CatalogNotFoundError("That character does not exist.")
    original = character.origin is CharacterOrigin.PROJECT_ORIGINAL
    warnings: list[str] = []
    describer = ReferenceManifests(session, catalog, projects=projects)

    standings: dict[uuid.UUID, ProjectStanding] = {}
    for row in session.execute(
        select(ProjectReferenceStanding).where(ProjectReferenceStanding.project_key == project_key)
    ).scalars():
        if row.character_id not in (None, character_id):
            continue
        current = standings.get(row.reference_id)
        if current is None or _STANDING_RANK[row.standing] < _STANDING_RANK[current]:
            standings[row.reference_id] = row.standing

    links = session.execute(
        select(ReferenceCharacter, ReferenceItem)
        .join(ReferenceItem, ReferenceItem.id == ReferenceCharacter.reference_id)
        .where(
            ReferenceCharacter.character_id == character_id,
            ReferenceItem.removed_at.is_(None),
        )
    ).all()

    facets: dict[str, list[dict[str, Any]]] = {name: [] for name in FACETS}
    not_selected: list[dict[str, Any]] = []
    described: dict[uuid.UUID, dict[str, Any]] = {}
    for link, item in links:
        facet = facet_of(link.aspect)
        lane = lane_of(item)
        standing = standings.get(item.id)
        reason = None
        if item.reference_class is ReferenceClass.UNSORTED:
            reason = "not sorted into canon, technique, continuity or mood yet"
        elif original and item.origin in _FRANCHISE_ORIGINS:
            reason = "an original project character is never grounded in franchise material"
        elif item.origin is ReferenceOrigin.FAN_ART and standing is None:
            reason = "fan art grounds a character only once this project gives it a standing"
        entry = {
            "reference_id": str(item.id),
            "aspect": link.aspect.value,
            "facet": facet,
            "lane": lane,
            "preferred": link.preferred,
            "project_standing": standing.value if standing else None,
            "outfit_id": str(link.outfit_id) if link.outfit_id else None,
            "label": item.label,
        }
        if reason is not None:
            not_selected.append({**entry, "reason": reason})
            continue
        if item.id not in described:
            described[item.id] = describer._reference(item, project_key, warnings)
        facets[facet].append({**entry, "reference": described[item.id]})

    for entries in facets.values():
        entries.sort(
            key=lambda e: (
                not e["preferred"],
                _STANDING_RANK.get(ProjectStanding(e["project_standing"]), 3)
                if e["project_standing"]
                else 3,
                e["reference"]["reference_class"] != ReferenceClass.CANON.value,
                e["reference_id"],
            )
        )

    documents: list[dict[str, Any]] = []
    for document_id in character.design_documents or []:
        found = (
            projects.document(character.project_key or project_key, str(document_id))
            if projects is not None
            else None
        )
        if found is None:
            warnings.append(f"design document {document_id} is not in the project")
            documents.append({"id": str(document_id), "available": False})
            continue
        _project, document, _text = found
        documents.append(
            {
                "id": document.id,
                "title": document.title,
                "lifecycle": document.lifecycle,
                "commit": document.commit,
                "available": True,
            }
        )

    styled = {
        str(row)
        for row in session.execute(
            select(ReferenceUseLink.reference_id).where(
                ReferenceUseLink.use == ReferenceUse.STYLE,
                ReferenceUseLink.reference_id.in_(
                    [uuid.UUID(e["reference_id"]) for f in facets.values() for e in f]
                    or [uuid.uuid4()]
                ),
            )
        ).scalars()
    }
    grounding: dict[str, list[str]] = {}
    stylization: set[str] = set()
    for name in REQUIRED_FACETS:
        chosen: list[str] = []
        for entry in facets[name]:
            origin = entry["reference"]["origin"]
            if original:
                # Only the creator's own references (photos) ground an original
                # character; concepts and generated art guide stylization only.
                photo = (
                    origin == ReferenceOrigin.USER_CREATED.value
                    and entry["reference_id"] not in styled
                )
                if photo:
                    chosen.append(entry["reference_id"])
                else:
                    stylization.add(entry["reference_id"])
            elif entry["lane"] in {"canonical_manga", "anime", "official_art"}:
                chosen.append(entry["reference_id"])
            else:
                stylization.add(entry["reference_id"])
        grounding[name] = list(dict.fromkeys(chosen))
    ungrounded = [name for name in REQUIRED_FACETS if not grounding[name]]
    missing = [name for name in REQUIRED_FACETS if not facets[name]]
    if original and missing:
        warnings.append(
            f"{character.display_name}: no project references for {', '.join(missing)} yet - "
            "import the creator-approved references; nothing is substituted"
        )
    lanes = dict.fromkeys(LANES, 0)
    for entries in facets.values():
        for entry in entries:
            lanes[entry["lane"]] += 1
    return {
        "character": {
            "id": str(character.id),
            "display_name": character.display_name,
            "origin": character.origin.value,
            "project_key": character.project_key,
            "subject_kind": character.subject_kind.value,
        },
        "project_key": project_key,
        "facets": facets,
        "lanes": lanes,
        "design_documents": documents,
        "missing": missing,
        "missing_optional": [
            name for name in FACETS if name not in REQUIRED_FACETS and not facets[name]
        ],
        "not_selected": not_selected,
        "usable": not missing,
        #: Required facets and the references that may ground them in generation.
        "grounding": grounding,
        "grounded": not ungrounded,
        "ungrounded": ungrounded,
        #: References that may guide style but never define identity or body.
        "stylization": sorted(stylization),
        "warnings": sorted(set(warnings)),
    }
