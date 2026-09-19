"""Visual Knowledge and layered-construction vocabulary (M3).

Visual Knowledge answers "how is this visual problem solved?". It is not a
second reference system: a Visual Knowledge item *is* a catalog reference,
its functions are :class:`~continuum_core.references.TechniqueFacet` values and
its descriptions are descriptor rows. What this module adds is what the
catalog did not have words for:

* **external resources** (datasets, annotation sets, models, tools) with a
  license, an access state and an allowed-use ceiling that no import can widen;
* the **knowledge uses** a resource or item may serve - looking, automatic
  retrieval into render packs, automated validation, training - kept apart so
  one never silently becomes another;
* the **construction stages** of a panel, what each stage may change and what
  it must leave as approved, and which techniques each stage looks up.

Pure data: no I/O, no framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from continuum_core.references import PanelStage, TechniqueFacet

__all__ = [
    "STAGE_CONTRACTS",
    "STAGE_FACETS",
    "STAGE_ORDER",
    "TRAINING_USES",
    "VISUAL_FUNCTION_FACETS",
    "AccessState",
    "KnowledgeUse",
    "ResourceKind",
    "StageContract",
    "stage_plan",
]


class KnowledgeUse(StrEnum):
    """What material may be used for. Each use is a separate, explicit decision."""

    REFERENCE_ONLY = "REFERENCE_ONLY"
    """A person may look at it. Nothing uses it automatically."""
    RETRIEVAL = "RETRIEVAL"
    """It may be retrieved automatically into a panel's reference pack."""
    VALIDATOR = "VALIDATOR"
    """It may drive automated checks (detectors, benchmarks). Never generation."""
    TRAINING_CANDIDATE = "TRAINING_CANDIDATE"
    """It may be proposed for a training manifest, pending rights review."""
    TRAINING_APPROVED = "TRAINING_APPROVED"
    """A person accepted its license and approved it for training."""


#: Uses that concern model training; none is ever granted by an import.
TRAINING_USES = frozenset({KnowledgeUse.TRAINING_CANDIDATE, KnowledgeUse.TRAINING_APPROVED})


class ResourceKind(StrEnum):
    """What an external resource is."""

    DATASET = "DATASET"
    ANNOTATIONS = "ANNOTATIONS"
    """Labels over images held elsewhere; the images keep their own terms."""
    MODEL = "MODEL"
    TOOL = "TOOL"
    RESEARCH = "RESEARCH"
    """A method or research project: architecture reference, not a dependency."""
    UNVERIFIED = "UNVERIFIED"
    """A suggestion nobody could match to a real, verifiable resource."""


class AccessState(StrEnum):
    """Whether Continuum's user may obtain the resource."""

    OPEN = "OPEN"
    """Public: no request needed."""
    NOT_REQUESTED = "NOT_REQUESTED"
    """Gated, registration or authorization required; not asked for yet."""
    REQUESTED = "REQUESTED"
    """Asked for; waiting on the provider."""
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


#: The Visual Knowledge functions (docs/creative/visual_knowledge item schema)
#: and the technique facet each is stored as. Total over the schema's list.
VISUAL_FUNCTION_FACETS: dict[str, TechniqueFacet] = {
    "CHARACTER_CONSTRUCTION": TechniqueFacet.ANATOMY,
    "ANATOMY": TechniqueFacet.ANATOMY,
    "HANDS": TechniqueFacet.HANDS,
    "FACE": TechniqueFacet.ANATOMY,
    "HAIR": TechniqueFacet.ANATOMY,
    "CLOTHING": TechniqueFacet.CLOTHING,
    "POSE": TechniqueFacet.POSE,
    "GESTURE": TechniqueFacet.POSE,
    "CAMERA": TechniqueFacet.CINEMATOGRAPHY,
    "PERSPECTIVE": TechniqueFacet.PERSPECTIVE,
    "COMPOSITION": TechniqueFacet.COMPOSITION,
    "ACTION": TechniqueFacet.ACTION_READABILITY,
    "IMPACT": TechniqueFacet.IMPACT_LANGUAGE,
    "MOTION": TechniqueFacet.MOTION_LANGUAGE,
    "EMOTION": TechniqueFacet.FACIAL_ACTING,
    "QUIET_ACTING": TechniqueFacet.QUIET_ACTING,
    "ENVIRONMENT": TechniqueFacet.BACKGROUND_TREATMENT,
    "ARCHITECTURE": TechniqueFacet.ARCHITECTURE,
    "MATERIALS": TechniqueFacet.MATERIALS,
    "LIGHTING": TechniqueFacet.LIGHTING,
    "ATMOSPHERE": TechniqueFacet.ATMOSPHERE,
    "MAGIC": TechniqueFacet.MAGIC,
    "FX": TechniqueFacet.FX,
    "LINEART": TechniqueFacet.LINEART,
    "SCREENTONE": TechniqueFacet.SCREENTONE,
    "COLOR": TechniqueFacet.COLOR,
    "MANGA_GRAMMAR": TechniqueFacet.MANGA_GRAMMAR,
    "PANEL_LAYOUT": TechniqueFacet.PAGE_COMPOSITION,
    "PAGE_TURN": TechniqueFacet.PAGE_TURN,
    "PROCESS": TechniqueFacet.PROCESS,
}


#: Build order. A stage only ever builds on the stages before it.
STAGE_ORDER: tuple[PanelStage, ...] = tuple(PanelStage)


@dataclass(frozen=True, slots=True)
class StageContract:
    """What a stage may change, and what stays as approved once it is frozen."""

    stage: PanelStage
    editable: tuple[str, ...]
    #: What this stage's approval freezes for every later stage.
    protects: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "editable": list(self.editable),
            "protects": list(self.protects),
        }


STAGE_CONTRACTS: dict[PanelStage, StageContract] = {
    c.stage: c
    for c in (
        StageContract(
            PanelStage.COMPOSITION,
            ("camera", "subject placement", "silhouettes", "depth", "perspective", "basic pose"),
            ("panel geometry", "camera", "placement", "spatial anchors", "cast count"),
        ),
        StageContract(
            PanelStage.DRAWING,
            ("anatomy", "faces", "hands", "hair", "clothing geometry", "props", "construction"),
            ("anatomy", "faces", "hands", "construction", "props"),
        ),
        StageContract(
            PanelStage.LINE,
            ("contours", "interior detail", "folds", "material boundaries"),
            ("line geometry",),
        ),
        StageContract(
            PanelStage.VALUE_MATERIAL,
            ("value masses", "material separation"),
            ("values", "materials"),
        ),
        StageContract(
            PanelStage.LIGHT_SHADOW,
            ("illumination", "cast shadows", "depth separation", "atmosphere"),
            ("lighting",),
        ),
        StageContract(
            PanelStage.FX,
            ("magic", "particles", "motion effects", "impact effects"),
            ("effects",),
        ),
        StageContract(
            PanelStage.ENVIRONMENT_INTEGRATION,
            ("background completion", "contact shadows", "environmental interaction"),
            ("integration",),
        ),
        StageContract(
            PanelStage.FINISH,
            ("ink finish", "screentone", "color finish", "cleanup"),
            ("finish",),
        ),
    )
}


#: The techniques each stage looks up: the narrowest evidence for its problem.
STAGE_FACETS: dict[PanelStage, tuple[TechniqueFacet, ...]] = {
    PanelStage.COMPOSITION: (
        TechniqueFacet.COMPOSITION,
        TechniqueFacet.CINEMATOGRAPHY,
        TechniqueFacet.PERSPECTIVE,
        TechniqueFacet.ESTABLISHING_SHOT,
        TechniqueFacet.NEGATIVE_SPACE,
        TechniqueFacet.PAGE_COMPOSITION,
    ),
    PanelStage.DRAWING: (
        TechniqueFacet.ANATOMY,
        TechniqueFacet.HANDS,
        TechniqueFacet.POSE,
        TechniqueFacet.CLOTHING,
        TechniqueFacet.FACIAL_ACTING,
        TechniqueFacet.QUIET_ACTING,
        TechniqueFacet.ACTION_READABILITY,
        TechniqueFacet.ARCHITECTURE,
        TechniqueFacet.BACKGROUND_TREATMENT,
    ),
    PanelStage.LINE: (TechniqueFacet.LINEART,),
    PanelStage.VALUE_MATERIAL: (TechniqueFacet.MATERIALS, TechniqueFacet.SCREENTONE),
    PanelStage.LIGHT_SHADOW: (
        TechniqueFacet.LIGHTING,
        TechniqueFacet.ATMOSPHERE,
        TechniqueFacet.NIGHT_RENDERING,
    ),
    PanelStage.FX: (
        TechniqueFacet.MAGIC,
        TechniqueFacet.FX,
        TechniqueFacet.IMPACT_LANGUAGE,
        TechniqueFacet.MOTION_LANGUAGE,
    ),
    PanelStage.ENVIRONMENT_INTEGRATION: (
        TechniqueFacet.BACKGROUND_TREATMENT,
        TechniqueFacet.ATMOSPHERE,
        TechniqueFacet.PERSPECTIVE,
    ),
    PanelStage.FINISH: (TechniqueFacet.SCREENTONE, TechniqueFacet.COLOR, TechniqueFacet.LINEART),
}


def stage_plan(*, has_cast: bool, needs_effects: bool) -> tuple[PanelStage, ...]:
    """The stages a panel is built in.

    Effects get a stage only when the panel has effects to draw; environment
    integration only when there is a cast to integrate. An environment-only
    panel is composed, drawn, lined, valued, lit and finished.
    """
    return tuple(
        stage
        for stage in STAGE_ORDER
        if (stage is not PanelStage.FX or needs_effects)
        and (stage is not PanelStage.ENVIRONMENT_INTEGRATION or has_cast)
    )
