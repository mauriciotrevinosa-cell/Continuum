"""Recurring objects that must keep their size (M3).

A brooch that is four centimetres across in one panel and the size of a hand in
the next is a continuity failure, and reference images alone do not fix it: a
renderer needs the measurement, expressed against something it can see.

A prop records what the object is, roughly how big it is, what its size reads
against (a head, a hand, a doorway), which references show it and - only when
the story gives it one - what it means. Approving a prop turns those numbers
into a **scale lock**: a short sentence that travels with every stage request
for a panel where the prop's owner appears.

The mechanism is generic. Nothing here knows any object, character or project.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Collection, Sequence
from typing import Any

from continuum_core.props import PropStatus, PropView, ScaleAnchor, describe_scale, describe_size
from continuum_db.models import ProjectProp, ProjectPropReference, ReferenceItem
from continuum_library import CatalogConflictError, CatalogInputError, CatalogNotFoundError
from continuum_library.validation import clean_text, require_project_key
from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = ["Props", "prop_view", "scale_lock"]

_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
_DIMENSIONS = ("length_mm", "width_mm", "height_mm", "diameter_mm")


def scale_lock(prop: ProjectProp) -> str:
    """The one sentence a renderer is told about this object, or "" if unknown."""
    parts = [text for text in (describe_size(prop.size), describe_scale(prop.body_scale)) if text]
    return f"{prop.name}: {', '.join(parts)}" if parts else ""


def prop_view(prop: ProjectProp, references: Sequence[ProjectPropReference] = ()) -> dict[str, Any]:
    return {
        "id": str(prop.id),
        "project_key": prop.project_key,
        "prop_key": prop.prop_key,
        "name": prop.name,
        "summary": prop.summary,
        "character_id": str(prop.character_id) if prop.character_id else None,
        "size": dict(prop.size or {}),
        "body_scale": dict(prop.body_scale or {}),
        "narrative_role": prop.narrative_role,
        "status": prop.status,
        "scale_lock": scale_lock(prop),
        "approved_by": prop.approved_by,
        "approved_at": prop.approved_at.isoformat() if prop.approved_at else None,
        "references": [
            {
                "id": str(link.id),
                "reference_id": str(link.reference_id),
                "view": link.view,
                "position": link.position,
                "notes": link.notes,
            }
            for link in sorted(references, key=lambda link: (link.position, str(link.id)))
        ],
    }


class Props:
    """Recurring objects, their measurements and the references that show them."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- reading --------------------------------------------------------------
    def get(self, prop_id: uuid.UUID) -> ProjectProp:
        prop = self.session.get(ProjectProp, prop_id)
        if prop is None:
            raise CatalogNotFoundError("That prop does not exist.")
        return prop

    def references(self, prop_id: uuid.UUID) -> list[ProjectPropReference]:
        return list(
            self.session.execute(
                select(ProjectPropReference)
                .where(ProjectPropReference.prop_id == prop_id)
                .order_by(ProjectPropReference.position, ProjectPropReference.id)
            ).scalars()
        )

    def all(self, project_key: str) -> list[dict[str, Any]]:
        props = list(
            self.session.execute(
                select(ProjectProp)
                .where(ProjectProp.project_key == require_project_key(project_key))
                .order_by(ProjectProp.name, ProjectProp.prop_key)
            ).scalars()
        )
        return [prop_view(prop, self.references(prop.id)) for prop in props]

    def for_characters(
        self, project_key: str, character_ids: Collection[uuid.UUID]
    ) -> list[dict[str, Any]]:
        """Approved props belonging to any of these characters, with their locks.

        Only approved props travel: a draft measurement is somebody thinking
        aloud, not a rule a render should be held to.
        """
        if not character_ids:
            return []
        props = list(
            self.session.execute(
                select(ProjectProp)
                .where(
                    ProjectProp.project_key == project_key,
                    ProjectProp.character_id.in_(list(character_ids)),
                    ProjectProp.status == PropStatus.APPROVED.value,
                )
                .order_by(ProjectProp.name, ProjectProp.prop_key)
            ).scalars()
        )
        return [prop_view(prop, self.references(prop.id)) for prop in props]

    # -- writing --------------------------------------------------------------
    def create(
        self,
        project_key: str,
        prop_key: str,
        name: str,
        *,
        character_id: uuid.UUID | None = None,
        summary: str = "",
        size: dict[str, Any] | None = None,
        body_scale: dict[str, Any] | None = None,
        narrative_role: str = "",
    ) -> ProjectProp:
        key = prop_key.strip().lower()
        if not _KEY.match(key):
            raise CatalogInputError(
                "A prop key is lowercase letters, digits and hyphens, starting with a "
                "letter or digit."
            )
        existing = self.session.execute(
            select(ProjectProp).where(
                ProjectProp.project_key == require_project_key(project_key),
                ProjectProp.prop_key == key,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise CatalogConflictError(f"This project already has a prop called {key!r}.")
        prop = ProjectProp(
            project_key=project_key,
            prop_key=key,
            name=clean_text(name, 200, field="Name"),
            summary=clean_text(summary, 4000, field="Summary") if summary else "",
            character_id=character_id,
            size=_clean_size(size),
            body_scale=_clean_scale(body_scale),
            narrative_role=(
                clean_text(narrative_role, 4000, field="Narrative role") if narrative_role else ""
            ),
            status=PropStatus.DRAFT.value,
        )
        self.session.add(prop)
        self.session.flush()
        return prop

    def update(
        self,
        prop_id: uuid.UUID,
        *,
        name: str | None = None,
        summary: str | None = None,
        size: dict[str, Any] | None = None,
        body_scale: dict[str, Any] | None = None,
        narrative_role: str | None = None,
        character_id: uuid.UUID | None = None,
    ) -> ProjectProp:
        prop = self.get(prop_id)
        if prop.status == PropStatus.APPROVED.value and (
            size is not None or body_scale is not None
        ):
            # Changing an approved measurement is re-approving it, deliberately.
            prop.status = PropStatus.DRAFT.value
            prop.approved_by, prop.approved_at = None, None
        if name is not None:
            prop.name = clean_text(name, 200, field="Name")
        if summary is not None:
            prop.summary = clean_text(summary, 4000, field="Summary") if summary else ""
        if size is not None:
            prop.size = _clean_size(size)
        if body_scale is not None:
            prop.body_scale = _clean_scale(body_scale)
        if narrative_role is not None:
            prop.narrative_role = (
                clean_text(narrative_role, 4000, field="Narrative role") if narrative_role else ""
            )
        if character_id is not None:
            prop.character_id = character_id
        self.session.flush()
        return prop

    def approve(self, prop_id: uuid.UUID, reviewer: str) -> ProjectProp:
        """Turn measurements into a lock. A prop with no measurements cannot lock."""
        prop = self.get(prop_id)
        who = reviewer.strip()
        if not who:
            raise CatalogInputError("A human reviewer is required.")
        if not scale_lock(prop):
            raise CatalogInputError(
                "This prop has no measurement to lock. Record a size, a body scale, "
                "or both, before approving it."
            )
        prop.status = PropStatus.APPROVED.value
        prop.approved_by, prop.approved_at = who[:200], dt.datetime.now(dt.UTC)
        self.session.flush()
        return prop

    def retire(self, prop_id: uuid.UUID) -> ProjectProp:
        prop = self.get(prop_id)
        prop.status = PropStatus.RETIRED.value
        prop.approved_by, prop.approved_at = None, None
        self.session.flush()
        return prop

    def add_reference(
        self,
        prop_id: uuid.UUID,
        reference_id: uuid.UUID,
        view: PropView,
        *,
        notes: str = "",
    ) -> ProjectPropReference:
        prop = self.get(prop_id)
        item = self.session.get(ReferenceItem, reference_id)
        if item is None or item.removed_at is not None:
            raise CatalogNotFoundError("That reference does not exist.")
        existing = self.session.execute(
            select(ProjectPropReference).where(
                ProjectPropReference.prop_id == prop.id,
                ProjectPropReference.reference_id == reference_id,
                ProjectPropReference.view == view.value,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise CatalogConflictError("That reference already shows this prop from that view.")
        link = ProjectPropReference(
            prop_id=prop.id,
            reference_id=reference_id,
            view=view.value,
            position=len(self.references(prop.id)),
            notes=clean_text(notes, 2000, field="Notes") if notes else "",
        )
        self.session.add(link)
        self.session.flush()
        return link


def _clean_size(size: dict[str, Any] | None) -> dict[str, Any]:
    if not size:
        return {}
    out: dict[str, Any] = {"approximate": bool(size.get("approximate", True))}
    for key in _DIMENSIONS:
        value = size.get(key)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise CatalogInputError(f"{key} must be a number of millimetres.") from exc
        if not 0 < number <= 100_000:
            raise CatalogInputError(f"{key} must be between 0 and 100000 millimetres.")
        out[key] = number
    return out


def _clean_scale(scale: dict[str, Any] | None) -> dict[str, Any]:
    if not scale:
        return {}
    anchor = str(scale.get("relative_to") or ScaleAnchor.NONE.value).upper()
    if anchor not in {item.value for item in ScaleAnchor}:
        raise CatalogInputError(
            "A body scale is measured against "
            + ", ".join(item.value.lower().replace("_", " ") for item in ScaleAnchor)
            + "."
        )
    if anchor == ScaleAnchor.NONE.value:
        return {}
    try:
        ratio = float(scale["ratio"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CatalogInputError("A body scale needs a ratio.") from exc
    if not 0 < ratio <= 50:
        raise CatalogInputError("A body-scale ratio must be between 0 and 50.")
    return {"relative_to": anchor, "ratio": ratio}
