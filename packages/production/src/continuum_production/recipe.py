"""Rough recipes: what an attempt is asked to be, and how it is to be made.

ADR-0005 splits a recipe in two, each hashed on its own:

* **intent** - the creative decision: target page/panel and panel-script
  revision, mode, characters with outfits and acting direction, visual modes,
  the reference bundle by role, the source plate, and edit operations
  (preserve / remove / replace / insert / ...) on regions of it;
* **execution** - the means: capability, workflow, requested provider, seed,
  output size, mask derivation, inpaint/control/strength/compositing settings.

The same schema describes a new generation, a source-derived edit, a
composite and a layout-only pass; the fields a real inpainting workflow will
need later (mask, strength, control inputs, crop, compositing) are part of
execution already, so Phase 1 recipes stay valid when a model arrives.

Validation here is structural and mode-aware. Everything that needs the
catalog (does the reference exist, is it previewable) happens in the service.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from continuum_core import NormalizedRegion, canonical_json_hash
from continuum_core.references import (
    BundleRole,
    CharacterAspect,
    EditOperationKind,
    RoughArtifactKind,
    RoughMode,
)
from continuum_library import CatalogInputError

__all__ = [
    "RECIPE_SCHEMA_VERSION",
    "TEMPLATE_PACKAGE_VERSION",
    "BundleEntry",
    "CharacterDirection",
    "EditOperation",
    "Placement",
    "RoughIntentSpec",
    "execution_document",
    "recipe_hashes",
    "regions_overlap",
]

RECIPE_SCHEMA_VERSION = 1
#: The prompt/template package a recipe was built against (ADR-0005 s.3).
TEMPLATE_PACKAGE_VERSION = "rough-recipe-1"
MAX_BUNDLE = 24
MAX_OPERATIONS = 32
MAX_PLACEMENTS = 16
MAX_EDGE = 2400
MIN_EDGE = 256
#: Operations that change pixels and therefore belong in the edit mask.
CHANGING = frozenset(EditOperationKind) - {EditOperationKind.PRESERVE}
_NEEDS_SUBJECT = frozenset(
    {
        EditOperationKind.REPLACE,
        EditOperationKind.INSERT,
        EditOperationKind.CHANGE_EXPRESSION,
        EditOperationKind.CHANGE_OUTFIT,
    }
)


@dataclass(frozen=True, slots=True)
class BundleEntry:
    """A catalog reference chosen for a role in this attempt."""

    role: BundleRole
    reference_id: uuid.UUID
    character_id: uuid.UUID | None = None
    outfit_id: uuid.UUID | None = None
    aspect: CharacterAspect | None = None
    label: str = ""
    #: Overrides the reference's own region for this attempt only.
    region: NormalizedRegion | None = None


@dataclass(frozen=True, slots=True)
class EditOperation:
    """An intended change to a region of the source plate (plate-crop coordinates)."""

    kind: EditOperationKind
    region: NormalizedRegion
    label: str = ""
    character_id: uuid.UUID | None = None
    outfit_id: uuid.UUID | None = None
    #: Bundle position of the reference this operation draws on, if any.
    reference_position: int | None = None
    text: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a character or element goes in a new, composite or layout frame."""

    region: NormalizedRegion
    label: str = ""
    character_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class CharacterDirection:
    """Who appears, wearing what, doing what - and in which visual mode, if any.

    A visual mode here changes how this character is *drawn in this attempt*
    (chibi compression, horror rendering); it never edits their identity.
    """

    character_id: uuid.UUID
    outfit_id: uuid.UUID | None = None
    acting_direction: str = ""
    visual_mode_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class RoughIntentSpec:
    """Everything a user decides for one attempt."""

    mode: RoughMode
    bundle: tuple[BundleEntry, ...] = ()
    characters: tuple[CharacterDirection, ...] = ()
    visual_mode_ids: tuple[uuid.UUID, ...] = ()
    operations: tuple[EditOperation, ...] = ()
    placements: tuple[Placement, ...] = ()
    #: For SOURCE_DERIVED_EDIT and COMPOSITE: the plate's crop, if not the whole unit.
    plate_region: NormalizedRegion | None = None
    brief: str = ""
    width: int | None = None
    height: int | None = None
    seed: int | None = None
    extra_execution: dict[str, Any] = field(default_factory=dict)

    def plates(self) -> list[int]:
        return [i for i, entry in enumerate(self.bundle) if entry.role is BundleRole.SOURCE_PLATE]

    def validate(self) -> None:
        """Mode rules and structural limits. Raises CatalogInputError."""
        if len(self.bundle) > MAX_BUNDLE:
            raise CatalogInputError(f"At most {MAX_BUNDLE} references in a bundle.")
        if len(self.operations) > MAX_OPERATIONS:
            raise CatalogInputError(f"At most {MAX_OPERATIONS} edit operations.")
        if len(self.placements) > MAX_PLACEMENTS:
            raise CatalogInputError(f"At most {MAX_PLACEMENTS} placements.")
        for edge in (self.width, self.height):
            if edge is not None and not MIN_EDGE <= edge <= MAX_EDGE:
                raise CatalogInputError(f"Output edges are {MIN_EDGE}-{MAX_EDGE} pixels.")
        if self.seed is not None and not 0 <= self.seed < 2**31:
            raise CatalogInputError("A seed is a non-negative 31-bit integer.")
        if len(set(self.visual_mode_ids)) != len(self.visual_mode_ids):
            raise CatalogInputError("A visual mode is listed twice.")
        if len({c.character_id for c in self.characters}) != len(self.characters):
            raise CatalogInputError("A character is directed twice.")

        plates = self.plates()
        changing = [op for op in self.operations if op.kind in CHANGING]
        if self.mode is RoughMode.SOURCE_DERIVED_EDIT:
            if len(plates) != 1:
                raise CatalogInputError(
                    "A source-derived edit starts from exactly one source plate."
                )
            if not changing:
                raise CatalogInputError(
                    "A source-derived edit says what changes: remove, replace, insert, redraw..."
                )
        elif self.mode is RoughMode.COMPOSITE:
            if not plates and not any(e.role is BundleRole.CONTINUITY for e in self.bundle):
                raise CatalogInputError(
                    "A composite combines at least one source plate or continuity element."
                )
            if len(self.bundle) < 2:
                raise CatalogInputError("A composite combines at least two elements.")
        elif self.mode is RoughMode.NEW_GENERATION:
            if plates or self.operations or self.plate_region is not None:
                raise CatalogInputError(
                    "A new generation has no source plate; use a source-derived edit or composite."
                )
            if not self.bundle and not self.characters:
                raise CatalogInputError("A new generation needs references or characters.")
        elif self.mode is RoughMode.LAYOUT_ONLY:
            if plates or self.operations or self.plate_region is not None:
                raise CatalogInputError("A layout-only pass places boxes; it edits no plate.")

        if self.plate_region is not None and not plates:
            raise CatalogInputError("A plate crop needs a source plate.")
        for op in self.operations:
            if op.reference_position is not None and not 0 <= op.reference_position < len(
                self.bundle
            ):
                raise CatalogInputError("An operation points at a reference not in the bundle.")
            if op.outfit_id is not None and op.character_id is None:
                raise CatalogInputError("An outfit change names the character.")
            if op.kind in _NEEDS_SUBJECT and not (
                op.character_id or op.reference_position is not None or op.label.strip()
            ):
                raise CatalogInputError(f"{op.kind.value} says who or what goes there.")
            if op.kind is EditOperationKind.REPLACE_TEXT and not op.text.strip():
                raise CatalogInputError("Replacing text needs the new text.")
        preserved = [op.region for op in self.operations if op.kind is EditOperationKind.PRESERVE]
        for op in changing:
            if any(regions_overlap(op.region, keep) for keep in preserved):
                raise CatalogInputError(
                    f"{op.kind.value} overlaps a region marked PRESERVE;"
                    " the intent contradicts itself."
                )


def regions_overlap(a: NormalizedRegion, b: NormalizedRegion) -> bool:
    """True when two regions share area (touching edges do not count)."""
    return (
        min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > 1e-9
        and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > 1e-9
    )


def execution_document(
    *,
    workflow: str,
    requested_provider: str | None,
    seed: int,
    width: int,
    height: int,
    plate_region: NormalizedRegion | None,
    has_mask: bool,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """The execution half, with every field a real edit workflow will need."""
    allowed_extra = {"strength", "inpaint", "control_inputs", "compositing", "post_processing"}
    # Page production (M3) names its artwork backend and that backend's settings.
    # Panel recipes never carry these keys, so their hashes are unchanged.
    page_extra = {"provider_id", "backend_settings"}
    unknown = set(extra) - allowed_extra - page_extra
    if unknown:
        raise CatalogInputError(f"Unknown execution settings: {', '.join(sorted(unknown))}.")
    page = {key: extra[key] for key in sorted(page_extra) if key in extra}
    return {
        **page,
        "schema": RECIPE_SCHEMA_VERSION,
        "capability": "ROUGH_RENDER",
        "workflow": workflow,
        "requested_provider": requested_provider,
        "model_ref": None,
        "seed": seed,
        "width": width,
        "height": height,
        "crop": plate_region.as_dict() if plate_region else None,
        "mask": "derived:changing-operations" if has_mask else None,
        "strength": extra.get("strength"),
        "inpaint": extra.get("inpaint") or {},
        "control_inputs": extra.get("control_inputs") or [],
        "compositing": extra.get("compositing") or {},
        "post_processing": extra.get("post_processing") or [],
    }


def recipe_hashes(intent: dict[str, Any], execution: dict[str, Any]) -> tuple[str, str]:
    return canonical_json_hash(intent), canonical_json_hash(execution)


def default_size(kind: RoughArtifactKind) -> tuple[int, int]:
    return (1000, 1414) if kind is RoughArtifactKind.PAGE else (1000, 700)
