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
