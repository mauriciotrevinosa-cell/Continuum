"""The panel-stage boundary for layered construction (M3).

``PageRenderProvider`` answers "render this page". A stage provider answers a
narrower question: *build this one construction stage of one panel* - on top of
the frozen output of the stage before it, changing only what the stage contract
lists as editable. Continuum owns the panel contract, the stage order, what is
frozen and when a stage becomes stale; a provider only draws.

Honesty rules, enforced by :func:`stage_gaps` and :func:`check_stage_result`:

* a provider declares which stages it can draw and whether it can hold a frozen
  upstream (a control input, a mask, a derivation) - a stage it cannot do is
  refused with the exact gap, never silently re-rendered from scratch;
* a stage built on an upstream keeps the upstream's geometry exactly;
* an ``ARTWORK_CANDIDATE`` reports backend, model (name, version, sha256,
  license, source), workflow (id, version, sha256) and settings, or is refused.

Conditioning has two lanes, kept apart in code and in provenance:

* **identity** - a named cast member's CANON references, one lane per character,
  never blended and never filled with anything else;
* **scene** - references that shape the setting and treatment (environment,
  place canon, house style, mood), with a purpose that depends on the stage:
  COMPOSITION takes layout and massing, later stages take style. Scene
  references are never identity evidence. Technique and grammar pages teach by
  abstraction and never image-condition (they are never a composition to copy).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from continuum_core.knowledge import STAGE_FACETS
from continuum_core.references import PanelStage, RenderOutput
from continuum_imaging import probe

from continuum_providers.artwork import (
    ArtworkBackendKind,
    ArtworkReference,
    RenderedImage,
)

__all__ = [
    "SCENE_BUDGET",
    "STAGE_SCENE_PURPOSE",
    "ConditioningPurpose",
    "PanelStageProvider",
    "PanelStageRequest",
    "PanelStageResult",
    "StageCapabilities",
    "check_stage_result",
    "scene_references",
    "stage_gaps",
]


class ConditioningPurpose(StrEnum):
    """What an image-conditioned reference is allowed to shape."""

    IDENTITY = "IDENTITY"
    """A named cast member's look. Only that character's CANON references."""
    COMPOSITION = "COMPOSITION"
    """Layout, massing and perspective of the setting."""
    STYLE_AND_COMPOSITION = "STYLE_AND_COMPOSITION"
    STYLE = "STYLE"
    """Line, value, light and finish treatment - never layout, never identity."""


#: The scene-lane purpose of each construction stage.
STAGE_SCENE_PURPOSE: dict[str, ConditioningPurpose] = {
    PanelStage.COMPOSITION.value: ConditioningPurpose.COMPOSITION,
    PanelStage.DRAWING.value: ConditioningPurpose.STYLE_AND_COMPOSITION,
    PanelStage.ENVIRONMENT_INTEGRATION.value: ConditioningPurpose.STYLE_AND_COMPOSITION,
    PanelStage.LINE.value: ConditioningPurpose.STYLE,
    PanelStage.VALUE_MATERIAL.value: ConditioningPurpose.STYLE,
    PanelStage.LIGHT_SHADOW.value: ConditioningPurpose.STYLE,
    PanelStage.FX.value: ConditioningPurpose.STYLE,
    PanelStage.FINISH.value: ConditioningPurpose.STYLE,
}
#: At most this many scene references condition one stage: evidence, not a pile.
SCENE_BUDGET = 2
#: Roles that may shape a stage's scene, best first, per purpose. A CANON
#: reference joins only when it names no character (place canon).
_SCENE_ROLES: dict[ConditioningPurpose, tuple[str, ...]] = {
    ConditioningPurpose.COMPOSITION: ("ENVIRONMENT", "CANON"),
    ConditioningPurpose.STYLE_AND_COMPOSITION: ("ENVIRONMENT", "CANON", "STYLE"),
    ConditioningPurpose.STYLE: ("STYLE", "ENVIRONMENT", "CANON", "MOOD"),
}
_NEVER_SCENE = {
    "TECHNIQUE": "technique pages teach by abstraction; never image-conditioned",
    "GRAMMAR": "grammar pages teach page structure; never image-conditioned",
    "WARDROBE": "wardrobe belongs to its wearer's lane; never scene conditioning",
    "CONTINUITY": "continuity pages show characters; never scene conditioning",
    "SOURCE_PLATE": "a source plate is edited, not a conditioning reference",
    "UPSTREAM_STAGE": "the upstream is held as the stage's base image",
}


def scene_references(
    request: PanelStageRequest, budget: int = SCENE_BUDGET
) -> tuple[ConditioningPurpose, list[ArtworkReference], list[dict[str, Any]]]:
    """The non-identity references that may image-condition this stage, best first.

    Returns (purpose, selected, not selected with the reason). Deterministic: role
    priority for the stage's purpose, then relevance to the stage's techniques,
    then the project's preferred look, then the order Continuum retrieved them in.
    """
    purpose = STAGE_SCENE_PURPOSE.get(request.stage, ConditioningPurpose.STYLE)
    roles = _SCENE_ROLES[purpose]
    stage_facets = {facet.value for facet in STAGE_FACETS.get(PanelStage(request.stage), ())}
    eligible: list[tuple[tuple[int, int, int, int], ArtworkReference]] = []
    skipped: list[dict[str, Any]] = []
    for order, reference in enumerate(request.references):
        provenance = reference.provenance or {}
        reason = None
        if reference.character:
            reason = "identity evidence of a cast member; identity lane only"
        elif reference.role in _NEVER_SCENE:
            reason = _NEVER_SCENE[reference.role]
        elif reference.role not in roles:
            reason = f"a {reference.role.lower()} reference does not shape {purpose.value.lower()}"
        elif provenance.get("status") == "CANDIDATE":
            reason = "an unconfirmed candidate"
        if reason is not None:
            skipped.append(
                {"reference_id": reference.reference_id, "role": reference.role, "reason": reason}
            )
            continue
        facets = {str(f).upper() for f in provenance.get("matched_facets") or []}
        rank = (
            roles.index(reference.role),
            0 if facets & stage_facets else 1,
            0 if provenance.get("standing") == "PREFERRED_FOR_CURRENT_LOOK" else 1,
            order,
        )
        eligible.append((rank, reference))
    eligible.sort(key=lambda pair: pair[0])
    selected = [reference for _rank, reference in eligible[:budget]]
    skipped.extend(
        {
            "reference_id": reference.reference_id,
            "role": reference.role,
            "reason": f"over the scene budget ({budget})",
        }
        for _rank, reference in eligible[budget:]
    )
    return purpose, selected, skipped


@dataclass(frozen=True, slots=True)
class StageCapabilities:
    """What a stage provider can really do - declared, never assumed."""

    output: RenderOutput
    #: PanelStage values this provider draws.
    stages: frozenset[str]
    #: Holds the frozen upstream structure (control input, mask or derivation).
    preserves_upstream: bool = False
    #: Conditions identity on character reference images.
    identity_conditioning: bool = False
    #: Conditions a stage on non-identity images (setting, house style) - the scene lane.
    reference_conditioning: bool = False
    #: May receive verbatim third-party source excerpts (never true for a remote
    #: provider unless the user explicitly allowed it).
    source_excerpts: bool = True
    renders_text: bool = False
    seeded: bool = False
    max_edge: int = 0
    available: bool = True
    notes: str = ""


@dataclass(frozen=True, slots=True)
class PanelStageRequest:
    stage: str
    #: The panel contract: beat, shot, cast, required anchors, forbidden content.
    contract: dict[str, Any]
    #: This stage's contract: what it may change and what everything before it froze.
    stage_contract: dict[str, Any]
    width: int
    height: int
    seed: int
    #: The frozen output of the previous stage; None for the first stage only.
    upstream: bytes | None
    upstream_stage: str | None
    references: tuple[ArtworkReference, ...]
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PanelStageResult:
    backend: ArtworkBackendKind
    provider_id: str
    output: RenderOutput
    image: RenderedImage
    #: backend, model{...}, workflow{...}, settings (as used), seed.
    provenance: dict[str, Any]


@runtime_checkable
class PanelStageProvider(Protocol):
    stage_capabilities: StageCapabilities
    backend: ArtworkBackendKind

    def render_stage(self, request: PanelStageRequest) -> PanelStageResult: ...


def stage_gaps(caps: StageCapabilities, request: PanelStageRequest) -> list[str]:
    """Every way the provider falls short of this stage request."""
    if not caps.available:
        return [caps.notes or "the stage backend is not available"]
    gaps = []
    if request.stage not in caps.stages:
        gaps.append(f"this backend does not draw the {request.stage} stage")
    if request.upstream is not None and not caps.preserves_upstream:
        gaps.append(
            f"{request.stage} must build on the frozen {request.upstream_stage} output; "
            "this backend cannot hold an upstream image"
        )
    cast = [str(name) for name in request.contract.get("cast") or []]
    grounded = {r.character for r in request.references if r.role == "CANON" and r.character}
    if cast and caps.output is RenderOutput.ARTWORK_CANDIDATE:
        if not caps.identity_conditioning:
            gaps.append("the panel's cast must be grounded in references; this backend cannot")
        for name in cast:
            if name not in grounded:
                # Environment, style and technique references never stand in for identity.
                gaps.append(
                    f"{name} has no identity evidence this backend may receive; "
                    "setting, style and technique references are never identity"
                )
    if caps.max_edge and max(request.width, request.height) > caps.max_edge:
        gaps.append(f"panel edge {max(request.width, request.height)} exceeds {caps.max_edge}")
    return gaps


_REQUIRED_MODEL = ("name", "version", "sha256", "license", "source")
_REQUIRED_WORKFLOW = ("id", "version", "sha256")


def check_stage_result(request: PanelStageRequest, result: PanelStageResult) -> list[str]:
    """Why a stage result cannot be recorded, or [] if it can.

    Geometry is checked against the upstream the stage was given: a stage that
    moves, crops or resizes the frozen structure is refused outright.
    """
    problems = []
    if request.upstream is not None:
        upstream = probe(request.upstream)
        if (result.image.width, result.image.height) != (upstream.width, upstream.height):
            problems.append(
                f"{request.stage} changed the frozen geometry "
                f"({upstream.width}x{upstream.height} -> "
                f"{result.image.width}x{result.image.height})"
            )
    elif (result.image.width, result.image.height) != (request.width, request.height):
        problems.append("the first stage does not have the panel's requested size")
    if result.output is RenderOutput.ARTWORK_CANDIDATE:
        prov = result.provenance or {}
        model = prov.get("model") or {}
        workflow = prov.get("workflow") or {}
        missing = [f"model.{k}" for k in _REQUIRED_MODEL if not model.get(k)]
        missing += [f"workflow.{k}" for k in _REQUIRED_WORKFLOW if not workflow.get(k)]
        missing += [k for k in ("settings", "backend") if not prov.get(k)]
        if missing:
            problems.append("artwork is not reproducible without " + ", ".join(missing))
    return problems
