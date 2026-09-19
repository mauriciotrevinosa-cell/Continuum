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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from continuum_core.references import RenderOutput
from continuum_imaging import probe

from continuum_providers.artwork import (
    ArtworkBackendKind,
    ArtworkReference,
    RenderedImage,
)

__all__ = [
    "PanelStageProvider",
    "PanelStageRequest",
    "PanelStageResult",
    "StageCapabilities",
    "check_stage_result",
    "stage_gaps",
]


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
    cast = {r.character for r in request.references if r.role == "CANON" and r.character}
    if cast and caps.output is RenderOutput.ARTWORK_CANDIDATE and not caps.identity_conditioning:
        gaps.append("the panel's cast must be grounded in references; this backend cannot")
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
