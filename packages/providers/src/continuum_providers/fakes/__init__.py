"""Deterministic fake providers (D-12, ADR-0004 section 6).

Phase 0 ships **no real AI SDK and downloads no model**. These fakes prove
the contract, the policy engine and the blocked/remediation path without any
network access or credential, which is exactly what acceptance test 110.12
requires.

Every fake is deterministic: identical input produces identical output, so a
job re-running a unit after a crash still satisfies the effect-idempotency
invariant of ADR-0002 section 2.
"""

from __future__ import annotations

import hashlib

from continuum_core import ProviderUnavailableError

from continuum_providers.contracts import (
    Capability,
    CostClass,
    GenerationRequest,
    GenerationResult,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)

__all__ = [
    "UNSATISFIABLE_CAPABILITY",
    "DeterministicEmbeddingProvider",
    "EchoTextProvider",
    "NullImageProvider",
]

#: A capability nothing in Phase 0 provides, used by the
#: synthetic.blocked_capability job to prove the BLOCKED path.
UNSATISFIABLE_CAPABILITY = Capability.VIDEO_GENERATE


class EchoTextProvider:
    """Returns its prompt back, plus a schema-shaped stub when asked."""

    descriptor = ProviderDescriptor(
        id="fake.echo-text",
        capabilities=frozenset({Capability.TEXT_GENERATE, Capability.TEXT_STRUCTURED}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. No model weights, no third-party code.",
    )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        structured = None
        if request.schema is not None:
            structured = {key: f"echo:{key}" for key in request.schema.get("properties", {})}
        return GenerationResult(
            provider_id=self.descriptor.id,
            model_ref=self.descriptor.model_ref,
            version=self.descriptor.version,
            text=request.prompt,
            structured=structured,
            usage={"data_class": request.data_class.value},
        )


class DeterministicEmbeddingProvider:
    """Hash-derived vectors: stable across runs, processes and machines."""

    DIMENSIONS = 16

    descriptor = ProviderDescriptor(
        id="fake.deterministic-embedding",
        capabilities=frozenset({Capability.EMBED_TEXT}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. No model weights.",
    )

    def embed(self, request: GenerationRequest) -> GenerationResult:
        digest = hashlib.sha256(request.prompt.encode()).digest()
        vector = tuple(
            (digest[i % len(digest)] / 255.0) * 2.0 - 1.0 for i in range(self.DIMENSIONS)
        )
        return GenerationResult(
            provider_id=self.descriptor.id,
            model_ref=self.descriptor.model_ref,
            version=self.descriptor.version,
            vector=vector,
            usage={"dimensions": self.DIMENSIONS, "data_class": request.data_class.value},
        )


class NullImageProvider:
    """Declares the capability and refuses to execute.

    Exists so the registry has a provider whose *selection* succeeds while
    its *invocation* fails -- the two failure modes must stay
    distinguishable, because they need different remediation.
    """

    descriptor = ProviderDescriptor(
        id="fake.null-image",
        capabilities=frozenset({Capability.IMAGE_GENERATE}),
        locality=Locality.LOCAL,
        cost_class=CostClass.FREE,
        privacy_class=PrivacyClass.ON_DEVICE,
        model_ref=None,
        version="1",
        license_note="Fake provider. Generates nothing.",
    )

    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        raise ProviderUnavailableError(
            "Image generation is not implemented in Phase 0.",
            technical_detail=f"data_class={request.data_class.value}",
            remediation=(
                "Visual Lab and image generation arrive in Phase 10 "
                "(Master Plan section 109). Phase 0 ships contracts only."
            ),
        )
