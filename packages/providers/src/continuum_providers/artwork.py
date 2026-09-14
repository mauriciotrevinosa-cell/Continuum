"""The artwork backend boundary for page-by-page manga production (M3).

Manga production asks one question of a backend: *render this page* - a
composition master and, from that same master, a black-and-white manga finish
and a color finish. Everything about *which* backend answers is here, so the
production semantics (runs, pages, continuity, review, invalidation) never
change when the backend does.

Backends:

* ``TEST`` - the deterministic sketch: proves the workflow, draws diagrams,
  always ``TEST_RENDER``;
* ``COMFY_LOCAL`` - a ComfyUI server on this machine (development and
  fallback; may be far too slow for final rendering);
* ``COMFY_REMOTE`` - a ComfyUI server elsewhere (an opportunistic free GPU
  session, or a machine the user controls). It receives only the page's
  materialized reference bundle, never the Vault;
* future providers implement the same protocol.

Honesty rules, enforced by :func:`check_result` and by the database:

* a backend declares what it can do (:class:`ArtworkCapabilities`); a request
  it cannot satisfy is refused with the exact gap, not silently degraded;
* an ``ARTWORK_CANDIDATE`` must report its backend, model (name, version,
  sha256, license, source), workflow (id, version, sha256) and the settings it
  actually used - otherwise it is not reproducible and is rejected;
* both finishes must have the master's exact dimensions and name the master
  they came from. Two unrelated compositions are never one page.

No paid service is reachable from here: a backend that costs money must be
added deliberately, with the user's approval, and declare ``CostClass.PAID``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from continuum_core.references import RenderOutput

__all__ = [
    "ArtworkBackendKind",
    "ArtworkCapabilities",
    "ArtworkCapabilityGapError",
    "ArtworkReference",
    "PageRenderProvider",
    "PageRenderRequest",
    "PageRenderResult",
    "RenderedImage",
    "capability_gaps",
    "check_result",
]


class ArtworkBackendKind(StrEnum):
    TEST = "TEST"
    COMFY_LOCAL = "COMFY_LOCAL"
    COMFY_REMOTE = "COMFY_REMOTE"


class ArtworkCapabilityGapError(RuntimeError):
    """The backend cannot do what the page needs. Carries every gap."""

    def __init__(self, gaps: Sequence[str]) -> None:
        super().__init__("; ".join(gaps))
        self.gaps = tuple(gaps)


@dataclass(frozen=True, slots=True)
class ArtworkCapabilities:
    """What a backend can really do - declared, inspectable, never assumed."""

    output: RenderOutput
    max_reference_images: int = 0
    #: Conditions identity on character reference images (e.g. an IP-adapter).
    identity_conditioning: bool = False
    #: Holds a layout/composition input (e.g. a control net over the master).
    layout_conditioning: bool = False
    #: Derives both finishes from one master (never two separate compositions).
    sibling_finishes: bool = False
    #: Draws the dialogue text itself. Continuum letters pages otherwise.
    renders_text: bool = False
    seeded: bool = False
    max_edge: int = 0
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ArtworkReference:
    """One reference in a page's bundle, by role, with its provenance."""

    role: str  # CANON | CONTINUITY | GRAMMAR | ENVIRONMENT | STYLE
    reference_id: str
    data: bytes
    character: str | None = None
    facet: str | None = None
    #: What this reference may teach: identity, layout, perspective, pacing...
    teaches: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PageRenderRequest:
    page_key: str
    width: int
    height: int
    seed: int
    #: The materialized page, the page plan (panels, shots, balloons) and the
    #: continuity context, as JSON-able dicts.
    page: dict[str, Any]
    plan: dict[str, Any]
    continuity: dict[str, Any]
    references: tuple[ArtworkReference, ...]
    #: Profile settings for this backend (checkpoint, workflow, steps, cfg...).
    settings: dict[str, Any]
    #: A previous approved master to keep geometry (regenerate-with-layout).
    layout_master: bytes | None = None


@dataclass(frozen=True, slots=True)
class RenderedImage:
    data: bytes
    mime: str
    width: int
    height: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True, slots=True)
class PageRenderResult:
    backend: ArtworkBackendKind
    provider_id: str
    output: RenderOutput
    master: RenderedImage
    bw: RenderedImage
    color: RenderedImage
    #: backend, model{name,version,sha256,license,source}, workflow{id,version,sha256},
    #: settings (as actually used), seed.
    provenance: dict[str, Any]


@runtime_checkable
class PageRenderProvider(Protocol):
    capabilities: ArtworkCapabilities
    backend: ArtworkBackendKind

    def render_page(self, request: PageRenderRequest) -> PageRenderResult: ...


def capability_gaps(caps: ArtworkCapabilities, request: PageRenderRequest) -> list[str]:
    """Every way the backend falls short of the request."""
    gaps = []
    needs_identity = any(r.role == "CANON" and r.character for r in request.references)
    if (
        needs_identity
        and caps.output is RenderOutput.ARTWORK_CANDIDATE
        and not caps.identity_conditioning
    ):
        gaps.append(
            "characters must be grounded in reference images; "
            "this backend cannot condition identity"
        )
    if (
        len(request.references) > caps.max_reference_images
        and caps.output is RenderOutput.ARTWORK_CANDIDATE
    ):
        gaps.append(
            f"the page needs {len(request.references)} reference images; "
            f"this backend accepts {caps.max_reference_images}"
        )
    if not caps.sibling_finishes:
        gaps.append("black-and-white and color must derive from one master; this backend cannot")
    if request.layout_master is not None and not caps.layout_conditioning:
        gaps.append("regenerating with a kept layout needs layout conditioning")
    if caps.max_edge and max(request.width, request.height) > caps.max_edge:
        gaps.append(f"page edge {max(request.width, request.height)} exceeds {caps.max_edge}")
    return gaps


_REQUIRED_MODEL = ("name", "version", "sha256", "license", "source")
_REQUIRED_WORKFLOW = ("id", "version", "sha256")


def check_result(result: PageRenderResult) -> list[str]:
    """Why a render result cannot be recorded, or [] if it can."""
    problems = []
    for name, image in (("black-and-white", result.bw), ("color", result.color)):
        if (image.width, image.height) != (result.master.width, result.master.height):
            problems.append(f"the {name} finish does not share the master's geometry")
    prov = result.provenance or {}
    if prov.get("master_sha256") not in (None, result.master.sha256):
        problems.append("the finishes name a different master")
    if result.output is RenderOutput.ARTWORK_CANDIDATE:
        model = prov.get("model") or {}
        workflow = prov.get("workflow") or {}
        missing = [f"model.{k}" for k in _REQUIRED_MODEL if not model.get(k)]
        missing += [f"workflow.{k}" for k in _REQUIRED_WORKFLOW if not workflow.get(k)]
        if not prov.get("settings"):
            missing.append("settings")
        if not prov.get("backend"):
            missing.append("backend")
        if missing:
            problems.append("artwork is not reproducible without " + ", ".join(missing))
    return problems
