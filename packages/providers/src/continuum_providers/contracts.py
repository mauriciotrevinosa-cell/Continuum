"""Provider contracts (ADR-0004 sections 1-2).

Shaped around Continuum's needs, not around any vendor's API. An interface
built from one vendor's ``messages``/``tools`` schema turns every local
adapter into a translation layer, which is how "model-agnostic" quietly dies.

``DataClass`` is **required** on every call and has no default. That is
deliberate: a defaulted privacy parameter is a forgotten privacy parameter,
and the first forgotten one silently ships source excerpts to a remote
provider. It is what makes the per-franchise LOCAL_ONLY flag of Master Plan
section 40 enforceable rather than decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from continuum_core import NormalizedRegion
from continuum_core.references import RenderOutput

__all__ = [
    "Capability",
    "CostClass",
    "DataClass",
    "EmbeddingProvider",
    "GenerationRequest",
    "GenerationResult",
    "ImageProvider",
    "Locality",
    "PrivacyClass",
    "Provider",
    "ProviderDescriptor",
    "RoughEditOperation",
    "RoughPlacement",
    "RoughReference",
    "RoughRenderProvider",
    "RoughRenderRequest",
    "RoughRenderResult",
    "TextProvider",
]


class Capability(StrEnum):
    """What a provider can do."""

    TEXT_GENERATE = "TEXT_GENERATE"
    TEXT_STRUCTURED = "TEXT_STRUCTURED"
    EMBED_TEXT = "EMBED_TEXT"
    EMBED_IMAGE = "EMBED_IMAGE"
    TRANSCRIBE = "TRANSCRIBE"
    IMAGE_GENERATE = "IMAGE_GENERATE"
    IMAGE_EDIT = "IMAGE_EDIT"
    SPEECH_SYNTHESIZE = "SPEECH_SYNTHESIZE"
    VIDEO_GENERATE = "VIDEO_GENERATE"
    ROUGH_RENDER = "ROUGH_RENDER"
    """A reviewable rough panel or page from a recipe: new, source-derived,
    composite or layout-only. Not final art (Phase 1 rough manga pipeline)."""
    PAGE_RENDER = "PAGE_RENDER"
    """A manga page: a composition master and its black-and-white and color
    finishes, from a materialized page and its reference bundle (M3)."""
    CHARACTER_MODEL_RENDER = "CHARACTER_MODEL_RENDER"
    """A standardized reference-grounded character model sheet candidate."""
    PANEL_STAGE_RENDER = "PANEL_STAGE_RENDER"
    """One construction stage of one panel, built on the frozen previous stage
    (layered construction, M3)."""


class Locality(StrEnum):
    """Where the computation happens."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"


class CostClass(StrEnum):
    """What using this provider costs the user."""

    FREE = "FREE"
    METERED = "METERED"
    PAID = "PAID"


class PrivacyClass(StrEnum):
    """What a provider may be trusted with."""

    ON_DEVICE = "ON_DEVICE"
    """Never leaves this machine."""

    SELF_HOSTED = "SELF_HOSTED"
    """Leaves the process but stays under the user's control."""

    THIRD_PARTY = "THIRD_PARTY"
    """Leaves the user's control entirely."""


class DataClass(StrEnum):
    """What kind of content a call is sending (F-37, F-54)."""

    SOURCE_EXCERPT = "SOURCE_EXCERPT"
    """Verbatim third-party source material. The most restricted class."""

    DERIVED_METADATA = "DERIVED_METADATA"
    """Hashes, durations, counts. Says nothing about content."""

    PROJECT_TEXT = "PROJECT_TEXT"
    """The user's own creative work."""

    USER_NOTE = "USER_NOTE"
    """The user's own annotations."""

    PROJECT_MEDIA = "PROJECT_MEDIA"
    """Images the user or the project made: creator references, approved project
    art, images the user created or commissioned, Continuum's own stage outputs."""

    SYNTHETIC = "SYNTHETIC"
    """Fixtures and tests. Unrestricted."""


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    """Everything the policy engine needs to decide about a provider.

    ``license_note`` covers BOTH code and model-weight terms (F-55). The
    dependency shortlist tracks code licences carefully and weight licences
    not at all, yet weights are what Continuum will actually download, and
    several carry non-commercial or likeness restrictions that bear directly
    on Master Plan section 2.8.
    """

    id: str
    capabilities: frozenset[Capability]
    locality: Locality
    cost_class: CostClass
    privacy_class: PrivacyClass
    model_ref: str | None = None
    version: str = "0"
    license_note: str = ""
    requirements: dict[str, Any] = field(default_factory=dict)
    #: What a ROUGH_RENDER image from this provider is evidence of. Defaults to
    #: a test render: a real generation provider must say it draws artwork.
    rough_output: RenderOutput = RenderOutput.TEST_RENDER

    def supports(self, capability: Capability) -> bool:
        return capability in self.capabilities


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """A request to a provider.

    ``data_class`` is positional-required by convention at every call site.
    """

    data_class: DataClass
    prompt: str = ""
    schema: dict[str, Any] | None = None
    max_tokens: int | None = None
    seed: int | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """What a provider returned, with the identity needed for reproducibility.

    ``provider_id``/``model_ref``/``version`` are recorded on the job so that
    Master Plan section 91.2's provider/model/recipe version requirement is
    satisfiable (and, later, ADR-0005's execution hash).
    """

    provider_id: str
    model_ref: str | None
    version: str
    text: str = ""
    structured: dict[str, Any] | None = None
    vector: tuple[float, ...] | None = None
    usage: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Provider(Protocol):
    """Base contract every provider satisfies."""

    descriptor: ProviderDescriptor


@runtime_checkable
class TextProvider(Provider, Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult: ...


@runtime_checkable
class EmbeddingProvider(Provider, Protocol):
    def embed(self, request: GenerationRequest) -> GenerationResult: ...


@runtime_checkable
class ImageProvider(Provider, Protocol):
    def generate_image(self, request: GenerationRequest) -> GenerationResult: ...


# ---------------------------------------------------------------------------
# Rough rendering (Phase 1, ADR-0005 recipes)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class RoughReference:
    """One bundle member handed to a renderer, with its role."""

    role: str
    label: str
    data: bytes
    region: NormalizedRegion | None = None


@dataclass(frozen=True, slots=True)
class RoughEditOperation:
    """An intended change to a region of the source plate (as cropped)."""

    kind: str
    region: NormalizedRegion
    label: str = ""


@dataclass(frozen=True, slots=True)
class RoughPlacement:
    """Where a character or element goes in a new or layout-only frame."""

    region: NormalizedRegion
    label: str = ""


@dataclass(frozen=True, slots=True)
class RoughRenderRequest:
    """Everything a renderer needs; bytes are handed in, never paths.

    ``plate`` is the source plate's unit bytes and ``plate_region`` its crop;
    ``mask`` marks the regions an edit may change (white) and must preserve
    (black), in plate-crop coordinates. A renderer returns a *new* image and
    never modifies what it was given.
    """

    data_class: DataClass
    mode: str
    width: int
    height: int
    seed: int
    title: str
    workflow: str
    lines: tuple[str, ...] = ()
    plate: bytes | None = None
    plate_region: NormalizedRegion | None = None
    mask: bytes | None = None
    operations: tuple[RoughEditOperation, ...] = ()
    placements: tuple[RoughPlacement, ...] = ()
    references: tuple[RoughReference, ...] = ()
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoughRenderResult:
    provider_id: str
    model_ref: str | None
    version: str
    workflow: str
    image: bytes
    mime: str
    width: int
    height: int
    usage: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class RoughRenderProvider(Provider, Protocol):
    def render_rough(self, request: RoughRenderRequest) -> RoughRenderResult: ...
